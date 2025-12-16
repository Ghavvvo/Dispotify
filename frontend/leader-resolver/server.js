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
      if (iface.family === 'IPv4' && !iface.internal) {
        return iface.address;
      }
    }
  }
  return 'unknown';
}

let cachedLeader = null;
let lastLeaderCheck = 0;
let cachedClusterNodes = [];
let lastNodesCheck = 0;
let lastReadNode = null; // Track the last node used for read operations
let lastReadNodeSongs = []; // Track the list of song IDs from the last read node

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
  
  // Return cached leader if still valid
  if (cachedLeader && (now - lastLeaderCheck) < LEADER_CACHE_TTL) {
    return cachedLeader;
  }

  const result = await discoverLeader();
  
  if (!result.leader) {
    throw new Error('No leader available');
  }

  if (cachedLeader && cachedLeader.leaderHost !== result.leader.leaderHost) {
    console.warn(`Leader changed: ${cachedLeader.leaderHost} → ${result.leader.leaderHost}`);
  }

  cachedLeader = result.leader;
  lastLeaderCheck = now;
  
  console.log(`Leader resolved: ${cachedLeader.leaderHost}:${cachedLeader.leaderPort}`);
  
  return cachedLeader;
}

async function getCachedClusterNodes() {
  const now = Date.now();
  
  // Return cached nodes if still valid
  if (cachedClusterNodes.length > 0 && (now - lastNodesCheck) < LEADER_CACHE_TTL) {
    return cachedClusterNodes;
  }

  const ips = await resolveClusterIPs();
  
  if (ips.length === 0) {
    throw new Error('No cluster nodes available');
  }

  cachedClusterNodes = ips.map(ip => ({
    host: ip,
    port: BACKEND_PORT
  }));
  lastNodesCheck = now;
  
  console.log(`Cluster nodes resolved: ${cachedClusterNodes.length} nodes`);
  
  return cachedClusterNodes;
}

function getRandomNode(nodes) {
  const randomIndex = Math.floor(Math.random() * nodes.length);
  return nodes[randomIndex];
}

function isReadOperation(method) {
  return method === 'GET' || method === 'HEAD' || method === 'OPTIONS';
}

async function getNodeSongs(node) {
  const url = `http://${node.host}:${node.port}/api/v1/cluster/files`;
  try {
    const response = await axios.get(url, { timeout: REQUEST_TIMEOUT });
    // Extract song IDs from metadata
    const songs = response.data.metadata || [];
    const songIds = songs.map(song => song.id).sort((a, b) => a - b);
    return songIds;
  } catch (error) {
    console.error(`Failed to get songs from node ${node.host}:${node.port}:`, error.message);
    return null; // Return null to indicate error
  }
}

function hasAllSongs(previousSongs, candidateSongs) {
  // Check if candidateSongs contains all songs from previousSongs
  if (!previousSongs || previousSongs.length === 0) {
    return true; // No previous songs to check
  }
  
  if (!candidateSongs) {
    return false; // Error getting candidate songs
  }
  
  const candidateSet = new Set(candidateSongs);
  
  for (const songId of previousSongs) {
    if (!candidateSet.has(songId)) {
      return false; // Missing song
    }
  }
  
  return true; // All songs present
}

async function selectReadNode(nodes) {
  // If no previous node, select a random one
  if (!lastReadNode) {
    const selectedNode = getRandomNode(nodes);
    const songs = await getNodeSongs(selectedNode);
    
    if (songs !== null) {
      lastReadNode = selectedNode;
      lastReadNodeSongs = songs;
      console.log(`  Initial read node selected: ${selectedNode.host}:${selectedNode.port} (${songs.length} songs: [${songs.join(', ')}])`);
    } else {
      console.log(`  Error getting songs from initial node, using it anyway: ${selectedNode.host}:${selectedNode.port}`);
    }
    
    return selectedNode;
  }

  // Check if the last read node is still in the available nodes
  const lastNodeStillAvailable = nodes.some(
    n => n.host === lastReadNode.host && n.port === lastReadNode.port
  );

  if (!lastNodeStillAvailable) {
    console.log(`  Last read node ${lastReadNode.host}:${lastReadNode.port} is no longer available`);
    // Select a new random node
    const selectedNode = getRandomNode(nodes);
    const songs = await getNodeSongs(selectedNode);
    
    if (songs !== null) {
      lastReadNode = selectedNode;
      lastReadNodeSongs = songs;
      console.log(`  New read node selected: ${selectedNode.host}:${selectedNode.port} (${songs.length} songs: [${songs.join(', ')}])`);
    } else {
      console.log(`  Error getting songs from new node, using it anyway: ${selectedNode.host}:${selectedNode.port}`);
    }
    
    return selectedNode;
  }

  // Try to select a different random node
  const candidateNode = getRandomNode(nodes);
  
  // If we randomly selected the same node, just use it
  if (candidateNode.host === lastReadNode.host && candidateNode.port === lastReadNode.port) {
    console.log(`  Keeping same read node: ${lastReadNode.host}:${lastReadNode.port}`);
    return lastReadNode;
  }

  // Get the candidate node's songs
  const candidateSongs = await getNodeSongs(candidateNode);
  
  if (candidateSongs === null) {
    // Error getting songs, keep using the last node
    console.log(`  Error checking candidate node, keeping last node: ${lastReadNode.host}:${lastReadNode.port}`);
    return lastReadNode;
  }

  // Check if the candidate has all songs from the previous node
  if (hasAllSongs(lastReadNodeSongs, candidateSongs)) {
    // Candidate has all required songs, switch to it
    const newSongs = candidateSongs.filter(id => !lastReadNodeSongs.includes(id));
    console.log(`  ✓ Switching read node: ${lastReadNode.host}:${lastReadNode.port} (${lastReadNodeSongs.length} songs) → ${candidateNode.host}:${candidateNode.port} (${candidateSongs.length} songs)`);
    if (newSongs.length > 0) {
      console.log(`    New songs in candidate: [${newSongs.join(', ')}]`);
    }
    lastReadNode = candidateNode;
    lastReadNodeSongs = candidateSongs;
    return candidateNode;
  } else {
    // Candidate is missing some songs, keep using the last node
    const missingSongs = lastReadNodeSongs.filter(id => !candidateSongs.includes(id));
    console.log(`  ✗ Candidate node missing ${missingSongs.length} song(s): [${missingSongs.join(', ')}]`);
    console.log(`    Keeping last node: ${lastReadNode.host}:${lastReadNode.port} (${lastReadNodeSongs.length} songs)`);
    return lastReadNode;
  }
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
      let target;
      let targetNode;
      const timestamp = new Date().toISOString();
      
      // Determine if this is a read or write operation
      if (isReadOperation(req.method)) {
        // For read operations, use smart node selection with sync verification
        const nodes = await getCachedClusterNodes();
        targetNode = await selectReadNode(nodes);
        target = `http://${targetNode.host}:${targetNode.port}`;
        console.log(`\n${'='.repeat(100)}`);
        console.log(`[${timestamp}] FRONTEND REQUEST (READ - LOAD BALANCED WITH SYNC CHECK)`);
      } else {
        // For write operations, always use the leader
        const leader = await getCachedLeader();
        targetNode = { host: leader.leaderHost, port: leader.leaderPort };
        target = `http://${targetNode.host}:${targetNode.port}`;
        console.log(`\n${'='.repeat(100)}`);
        console.log(`[${timestamp}] FRONTEND REQUEST (WRITE - TO LEADER)`);
        
        // After a write, invalidate the last read node info to force re-check
        console.log(`  Invalidating read node cache after write operation`);
        lastReadNode = null;
        lastReadNodeSongs = [];
      }
      
      console.log(`  Method: ${req.method}`);
      console.log(`  URL: ${req.url}`);
      console.log(`  Headers: ${JSON.stringify(req.headers, null, 2)}`);
      
      if (req.body && Object.keys(req.body).length > 0) {
        console.log(`  Body: ${JSON.stringify(req.body, null, 2)}`);
      } else {
        console.log(`  Body: (empty)`);
      }
      
      console.log(`\n PROXYING TO BACKEND`);
      console.log(`  Target Node: ${targetNode.host}:${targetNode.port}`);
      console.log(`  Target URL: ${target}${req.url}`);
      console.log(`  Method: ${req.method}`);
      
      return target;
    } catch (error) {
      console.error(`[PROXY] ❌ Failed to resolve target: ${error.message}`);
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
    
    // Invalidate caches on error to force rediscovery
    console.warn(' Invalidating caches due to proxy error');
    cachedLeader = null;
    lastLeaderCheck = 0;
    cachedClusterNodes = [];
    lastNodesCheck = 0;
    lastReadNode = null;
    lastReadNodeSongs = [];
    
    if (!res.headersSent) {
      res.status(503).json({
        error: 'Service Unavailable',
        message: 'Could not proxy request to backend',
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
      // Static files are read operations, use smart node selection
      const nodes = await getCachedClusterNodes();
      const targetNode = await selectReadNode(nodes);
      const target = `http://${targetNode.host}:${targetNode.port}`;
      console.log(`[PROXY] Static file ${req.url} → ${target} (load balanced with sync check)`);
      return target;
    } catch (error) {
      console.error('[PROXY] Failed to resolve node for static file:', error.message);
      throw error;
    }
  },
  onError: (err, req, res) => {
    console.error('[PROXY] Static file error:', err.message);
    
    console.warn('Invalidating caches due to static file error');
    cachedLeader = null;
    lastLeaderCheck = 0;
    cachedClusterNodes = [];
    lastNodesCheck = 0;
    lastReadNode = null;
    lastReadNodeSongs = [];
    
    res.status(503).send('Service Unavailable');
  }
}));

app.listen(SERVICE_PORT, () => {
  console.log(`Leader Proxy running on port ${SERVICE_PORT}`);
  console.log(`Configuration:`);
  console.log(`  - CLUSTER_DNS_NAME: ${CLUSTER_DNS_NAME}`);
  console.log(`  - BACKEND_PORT: ${BACKEND_PORT}`);
  console.log(`  - LEADER_ENDPOINT: ${LEADER_ENDPOINT}`);
  console.log(`  - LEADER_CACHE_TTL: ${LEADER_CACHE_TTL}ms`);
  console.log(`\nProxy endpoints:`);
  console.log(`  - /api/* → Load balanced (READ) or Leader (WRITE)`);
  console.log(`  - /static/* → Load balanced across cluster nodes`);
  console.log(`  - /health → Proxy health check`);
  console.log(`  - /cluster/leader → Leader info`);
  console.log(`\nLoad balancing strategy:`);
  console.log(`  - GET/HEAD/OPTIONS requests → Smart node selection (sync-aware load balancing)`);
  console.log(`  - POST/PUT/DELETE requests → Leader node only`);
  console.log(`\nSync verification:`);
  console.log(`  - New nodes must contain ALL songs from previous node before switching`);
  console.log(`  - Song lists are compared by ID to ensure data consistency`);
  console.log(`  - Read node cache invalidated after write operations`);
});
