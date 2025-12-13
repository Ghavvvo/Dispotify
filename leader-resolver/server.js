const express = require('express');
const dns = require('dns').promises;
const axios = require('axios');

const app = express();

// Configuration from environment variables
const CLUSTER_DNS_NAME = process.env.CLUSTER_DNS_NAME || 'dispotify-cluster';
const BACKEND_PORT = parseInt(process.env.BACKEND_PORT, 10) || 8000;
const LEADER_ENDPOINT = process.env.LEADER_ENDPOINT || '/cluster/leader';
const SERVICE_PORT = parseInt(process.env.SERVICE_PORT, 10) || 3000;
const REQUEST_TIMEOUT = parseInt(process.env.REQUEST_TIMEOUT, 10) || 3000;

/**
 * Resolve all IPs associated with the cluster DNS name
 */
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

/**
 * Query a single node for its leader information
 */
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

/**
 * Discover the cluster leader by querying all nodes and voting
 */
async function discoverLeader() {
  const ips = await resolveClusterIPs();
  
  if (ips.length === 0) {
    return { error: 'No cluster nodes found', leader: null };
  }

  // Query all nodes in parallel
  const responses = await Promise.all(ips.map(ip => queryNodeForLeader(ip)));
  
  // Count votes for each leader
  const votes = {};
  
  for (const response of responses) {
    if (response && response.leaderHost) {
      const leaderKey = `${response.leaderHost}:${response.leaderPort || BACKEND_PORT}`;
      votes[leaderKey] = (votes[leaderKey] || 0) + 1;
    }
  }

  console.log('Leader votes:', votes);

  // Find the leader with most votes
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

// Health check endpoint
app.get('/health', (req, res) => {
  res.json({ status: 'ok', service: 'leader-resolver' });
});

// Main endpoint to get the cluster leader
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

app.listen(SERVICE_PORT, () => {
  console.log(`Leader resolver service running on port ${SERVICE_PORT}`);
  console.log(`Configuration:`);
  console.log(`  - CLUSTER_DNS_NAME: ${CLUSTER_DNS_NAME}`);
  console.log(`  - BACKEND_PORT: ${BACKEND_PORT}`);
  console.log(`  - LEADER_ENDPOINT: ${LEADER_ENDPOINT}`);
});
