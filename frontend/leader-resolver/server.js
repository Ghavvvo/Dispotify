const express = require('express');
const dns = require('dns').promises;
const axios = require('axios');
const { createProxyMiddleware } = require('http-proxy-middleware');
const os = require('os');

const app = express();

const CLUSTER_DNS_NAME = process.env.CLUSTER_DNS_NAME || 'dispotify-cluster';
const BACKEND_PORT = parseInt(process.env.BACKEND_PORT, 10) || 8000;
const LEADER_ENDPOINT = process.env.LEADER_ENDPOINT || '/cluster/leader';
const SERVICE_PORT = parseInt(process.env.SERVICE_PORT, 10) || 3000;
const REQUEST_TIMEOUT = parseInt(process.env.REQUEST_TIMEOUT, 10) || 3000;
const LEADER_CACHE_TTL = parseInt(process.env.LEADER_CACHE_TTL, 10) || 5000;

const PROXY_HOSTNAME = os.hostname();
const PROXY_IP = getProxyIP();


function getProxyIP() {
  const interfaces = os.networkInterfaces();
  for (const name of Object.keys(interfaces)) {
    for (const iface of interfaces[name]) {
      // Skip internal and non-IPv4 addresses
      if (iface.family === 'IPv4' && !iface.internal) {
        return iface.address;
      }
    }
  }
  return 'unknown';
}

let cachedLeader = null;
let lastLeaderCheck = 0;

async function resolveClusterIPs() {
  try {
    const addresses = await dns.resolve4(CLUSTER_DNS_NAME);
    console.log(`Resolved ${addresses.length} IPs for ${CLUSTER_DNS_NAME}:`, addresses);
    return addresses;
  } catch (error) {
    console.error(`Failed to resolve DNS for ${CLUSTER_DNS_NAME}:`, error.message);
    return [];
  }
}

async function queryNodeForLeader(ip) {
  const url = `http://${ip}:${BACKEND_PORT}${LEADER_ENDPOINT}`;
  try {
    const response = await axios.get(url, { timeout: REQUEST_TIMEOUT });
    console.log(`Node ${ip} responded:`, response.data);
    return response.data;
  } catch (error) {
    console.error(`Failed to query node ${ip}:`, error.message);
    return null;
  }
}


async function discoverLeader() {
  const ips = await resolveClusterIPs();
  
  if (ips.length === 0) {
    return { error: 'No cluster nodes found', leader: null };
  }

  const responses = await Promise.all(ips.map(ip => queryNodeForLeader(ip)));
  
  const votes = {};
  
  for (const response of responses) {
    if (response && response.leaderHost) {
      const leaderKey = `${response.leaderHost}:${response.leaderPort || BACKEND_PORT}`;
      votes[leaderKey] = (votes[leaderKey] || 0) + 1;
    }
  }

  console.log('Leader votes:', votes);

  let maxVotes = 0;
  let electedLeader = null;

  for (const [leaderKey, voteCount] of Object.entries(votes)) {
    if (voteCount > maxVotes) {
      maxVotes = voteCount;
      const [host, port] = leaderKey.split(':');
      electedLeader = {
        leaderHost: host,
        leaderPort: parseInt(port, 10)
      };
    }
  }

  return { leader: electedLeader, votes, totalNodes: ips.length };
}


async function getCachedLeader() {
  const now = Date.now();
  
  if (cachedLeader && (now - lastLeaderCheck) < LEADER_CACHE_TTL) {
    return cachedLeader;
  }

  const result = await discoverLeader();
  
  if (!result.leader) {
    throw new Error('No leader available');
  }

  if (cachedLeader && cachedLeader.leaderHost !== result.leader.leaderHost) {
    console.warn(`⚠️ Leader changed: ${cachedLeader.leaderHost} → ${result.leader.leaderHost}`);
  }

  cachedLeader = result.leader;
  lastLeaderCheck = now;
  
  console.log(`Leader resolved: ${cachedLeader.leaderHost}:${cachedLeader.leaderPort}`);
  
  return cachedLeader;
}

app.use((req, res, next) => {
  res.header('Access-Control-Allow-Origin', '*');
  res.header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS');
  res.header('Access-Control-Allow-Headers', 'Origin, X-Requested-With, Content-Type, Accept, Authorization');
  
  if (req.method === 'OPTIONS') {
    return res.sendStatus(200);
  }
  
  next();
});

app.get('/health', (req, res) => {
  res.json({ status: 'ok', service: 'leader-proxy' });
});

app.get('/cluster/leader', async (req, res) => {
  try {
    const result = await discoverLeader();
    
    if (!result.leader) {
      return res.status(503).json({
        error: 'No leader available',
        message: 'Could not determine cluster leader. No valid responses from nodes.',
        totalNodes: result.totalNodes || 0
      });
    }

    res.json({
      leaderHost: result.leader.leaderHost,
      leaderPort: result.leader.leaderPort,
      confidence: result.votes ? Object.values(result.votes).reduce((a, b) => a + b, 0) : 0,
      totalNodes: result.totalNodes
    });
  } catch (error) {
    console.error('Error discovering leader:', error);
    res.status(500).json({
      error: 'Internal server error',
      message: error.message
    });
  }
});

app.use('/api', express.json());
app.use('/api', express.urlencoded({ extended: true }));

app.use('/api', createProxyMiddleware({
  target: 'http://placeholder', // Will be overridden by router
  changeOrigin: true,
  pathRewrite: (path, req) => {
    if (!path.endsWith('/') && !path.includes('.') && !path.includes('?') && !path.includes('/upload')) {
      console.log(`[PATH REWRITE] Adding trailing slash: ${path} → ${path}/`);
      return path + '/';
    }
    return path;
  },
  router: async (req) => {
    try {
      const leader = await getCachedLeader();
      const target = `http://${leader.leaderHost}:${leader.leaderPort}`;
      const timestamp = new Date().toISOString();
      
      console.log(`\n${'='.repeat(100)}`);
      console.log(`[${timestamp}] 📥 FRONTEND REQUEST`);
      console.log(`  Method: ${req.method}`);
      console.log(`  URL: ${req.url}`);
      console.log(`  Headers: ${JSON.stringify(req.headers, null, 2)}`);
      
      if (req.body && Object.keys(req.body).length > 0) {
        console.log(`  Body: ${JSON.stringify(req.body, null, 2)}`);
      } else {
        console.log(`  Body: (empty)`);
      }
      
      console.log(`\n🔄 PROXYING TO BACKEND`);
      console.log(`  Target URL: ${target}${req.url}`);
      console.log(`  Method: ${req.method}`);
      
      return target;
    } catch (error) {
      console.error(`[PROXY] ❌ Failed to resolve leader: ${error.message}`);
      throw error;
    }
  },
  onProxyReq: (proxyReq, req, res) => {
    if (req.body && Object.keys(req.body).length > 0) {
      const bodyData = JSON.stringify(req.body);
      proxyReq.setHeader('Content-Type', 'application/json');
      proxyReq.setHeader('Content-Length', Buffer.byteLength(bodyData));
      proxyReq.write(bodyData);
      console.log(`  Body sent to backend: ${bodyData}`);
    } else {
      console.log(`  Body sent to backend: (empty)`);
    }
  },
  onError: (err, req, res) => {
    const timestamp = new Date().toISOString();
    console.error(`\n${'!'.repeat(100)}`);
    console.error(`[${timestamp}] ❌ PROXY ERROR`);
    console.error(`  Method: ${req.method}`);
    console.error(`  URL: ${req.url}`);
    console.error(`  Error: ${err.message}`);
    console.error(`${'!'.repeat(100)}\n`);
    
    console.warn('Invalidating leader cache due to proxy error');
    cachedLeader = null;
    lastLeaderCheck = 0;
    
    if (!res.headersSent) {
      res.status(503).json({
        error: 'Service Unavailable',
        message: 'Could not proxy request to leader',
        details: err.message
      });
    }
  },
  onProxyRes: (proxyRes, req, res) => {
    const timestamp = new Date().toISOString();
    const contentLength = proxyRes.headers['content-length'] || '?';
    
    res.setHeader('X-Proxy-Hostname', PROXY_HOSTNAME);
    res.setHeader('X-Proxy-IP', PROXY_IP);
    res.setHeader('X-Proxy-Port', SERVICE_PORT.toString());
    
    if (proxyRes.headers['x-node-id']) {
      res.setHeader('X-Backend-Node-ID', proxyRes.headers['x-node-id']);
    }
    if (proxyRes.headers['x-node-hostname']) {
      res.setHeader('X-Backend-Node-Hostname', proxyRes.headers['x-node-hostname']);
    }
    if (proxyRes.headers['x-node-ip']) {
      res.setHeader('X-Backend-Node-IP', proxyRes.headers['x-node-ip']);
    }
    if (proxyRes.headers['x-node-port']) {
      res.setHeader('X-Backend-Node-Port', proxyRes.headers['x-node-port']);
    }
    
    const existingExposeHeaders = res.getHeader('Access-Control-Expose-Headers') || '';
    const newExposeHeaders = [
      existingExposeHeaders,
      'X-Proxy-Hostname',
      'X-Proxy-IP',
      'X-Proxy-Port',
      'X-Backend-Node-ID',
      'X-Backend-Node-Hostname',
      'X-Backend-Node-IP',
      'X-Backend-Node-Port'
    ].filter(Boolean).join(', ');
    res.setHeader('Access-Control-Expose-Headers', newExposeHeaders);
    
    let backendResponseBody = '';
    proxyRes.on('data', (chunk) => {
      backendResponseBody += chunk.toString('utf8');
    });
    
    proxyRes.on('end', () => {
      console.log(`\n BACKEND RESPONSE`);
      console.log(`  Status: ${proxyRes.statusCode} ${proxyRes.statusMessage}`);
      console.log(`  Content-Type: ${proxyRes.headers['content-type'] || 'unknown'}`);
      console.log(`  Content-Length: ${contentLength} bytes`);
      console.log(`  Backend Node ID: ${proxyRes.headers['x-node-id'] || 'unknown'}`);
      console.log(`  Backend Node Hostname: ${proxyRes.headers['x-node-hostname'] || 'unknown'}`);
      
      try {
        const jsonData = JSON.parse(backendResponseBody);
        console.log(`  Body: ${JSON.stringify(jsonData, null, 2)}`);
      } catch (e) {
        const preview = backendResponseBody.length > 500 ? backendResponseBody.substring(0, 500) + '...' : backendResponseBody;
        console.log(`  Body: ${preview || '(empty)'}`);
      }
      
      console.log(`\n RESPONSE TO FRONTEND`);
      console.log(`  Status: ${proxyRes.statusCode}`);
      console.log(`  Proxy Hostname: ${PROXY_HOSTNAME}`);
      console.log(`  Proxy IP: ${PROXY_IP}`);
      console.log(`  Same body as backend response`);
      console.log(`${'='.repeat(100)}\n`);
    });
  }
}));

app.use('/static', createProxyMiddleware({
  target: 'http://placeholder',
  changeOrigin: true,
  router: async (req) => {
    try {
      const leader = await getCachedLeader();
      const target = `http://${leader.leaderHost}:${leader.leaderPort}`;
      console.log(`[PROXY] Static file ${req.url} → ${target}`);
      return target;
    } catch (error) {
      console.error('[PROXY] Failed to resolve leader for static file:', error.message);
      throw error;
    }
  },
  onError: (err, req, res) => {
    console.error('[PROXY] Static file error:', err.message);
    
    console.warn('Invalidating leader cache due to static file error');
    cachedLeader = null;
    lastLeaderCheck = 0;
    
    res.status(503).send('Service Unavailable');
  }
}));

app.listen(SERVICE_PORT, () => {
  console.log(`\n Leader Proxy running on port ${SERVICE_PORT}`);
  console.log(`Configuration:`);
  console.log(`  - CLUSTER_DNS_NAME: ${CLUSTER_DNS_NAME}`);
  console.log(`  - BACKEND_PORT: ${BACKEND_PORT}`);
  console.log(`  - LEADER_ENDPOINT: ${LEADER_ENDPOINT}`);
  console.log(`  - LEADER_CACHE_TTL: ${LEADER_CACHE_TTL}ms`);
  console.log(`\nProxy endpoints:`);
  console.log(`  - /api/* → Leader backend`);
  console.log(`  - /static/* → Leader static files`);
  console.log(`  - /health → Proxy health check`);
  console.log(`  - /cluster/leader → Leader info`);
});
