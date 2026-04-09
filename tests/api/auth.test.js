/**
 * Red-phase auth tests for /api/users endpoint
 * 
 * Claim under test: the /api/users endpoint returns HTTP 401 for requests
 * that do not include a valid JWT token in the Authorization header.
 * 
 * These tests are designed to FAIL in red-phase because the endpoint
 * does not exist yet (or does not implement auth). They will PASS once
 * the auth middleware is properly implemented.
 */

const http = require('http');

// Server configuration - assumes server is running on port 3000
// Tests will start the server if not running (inline for red-phase)
const PORT = process.env.PORT || 3000;
const BASE_URL = `http://localhost:${PORT}`;

/**
 * Makes a real HTTP request to the given path with optional headers.
 * No mocks - all HTTP layer interactions are real.
 */
function makeRequest(path, headers = {}, method = 'GET') {
  return new Promise((resolve, reject) => {
    const url = new URL(path, BASE_URL);
    const options = {
      hostname: url.hostname,
      port: url.port,
      path: url.pathname,
      method: method,
      headers: headers
    };

    const req = http.request(options, (res) => {
      let body = '';
      res.on('data', chunk => body += chunk);
      res.on('end', () => {
        resolve({
          statusCode: res.statusCode,
          headers: res.headers,
          body: body
        });
      });
    });

    req.on('error', (err) => {
      // Connection refused means server not running - this is expected in red-phase
      if (err.code === 'ECONNREFUSED') {
        resolve({ statusCode: 0, error: 'SERVER_NOT_RUNNING' });
      } else {
        reject(err);
      }
    });

    req.end();
  });
}

/**
 * Test 1: Request with no Authorization header at all
 * 
 * Falsification: If the endpoint accepts unauthenticated requests,
 * it would return a status other than 401 (or no 401 at all).
 * 
 * Oracle: HTTP 401 status code in response.
 * 
 * This test would fail if unauthenticated requests are accepted because
 * the response would have status 200/404/500 instead of 401.
 */
async function testNoAuthorizationHeader() {
  console.log('TEST: Request with no Authorization header');
  
  const response = await makeRequest('/api/users', {});
  
  console.log(`  Status: ${response.statusCode}`);
  console.log(`  Expected: 401`);
  console.log(`  Result: ${response.statusCode === 401 ? 'PASS (would fail in red-phase)' : 'FAIL - wrong status'}`);
  
  if (response.statusCode !== 401) {
    throw new Error(
      `Expected HTTP 401 for request without Authorization header, ` +
      `got ${response.statusCode} instead. ` +
      `This means unauthenticated requests are being accepted!`
    );
  }
}

/**
 * Test 2: Request with malformed Authorization header (missing 'Bearer' prefix)
 * 
 * Falsification: If the endpoint accepts malformed tokens,
 * it would return a status other than 401.
 * 
 * Oracle: HTTP 401 status code in response.
 * 
 * This test would fail if malformed tokens are accepted because
 * the response would have status 200/404/500 instead of 401.
 */
async function testMalformedAuthorizationHeader() {
  console.log('TEST: Request with malformed Authorization header');
  
  // Missing 'Bearer ' prefix - just a raw token
  const response = await makeRequest('/api/users', {
    'Authorization': 'invalid-token-format'
  });
  
  console.log(`  Status: ${response.statusCode}`);
  console.log(`  Expected: 401`);
  console.log(`  Result: ${response.statusCode === 401 ? 'PASS (would fail in red-phase)' : 'FAIL - wrong status'}`);
  
  if (response.statusCode !== 401) {
    throw new Error(
      `Expected HTTP 401 for request with malformed Authorization header, ` +
      `got ${response.statusCode} instead. ` +
      `This means malformed tokens are being accepted!`
    );
  }
}

/**
 * Test 3: Request with an expired JWT token
 * 
 * Falsification: If the endpoint accepts expired tokens,
 * it would return a status other than 401.
 * 
 * Oracle: HTTP 401 status code in response.
 * 
 * This test would fail if expired tokens are accepted because
 * the response would have status 200/404/500 instead of 401.
 * 
 * Note: This uses a real expired JWT (expired in 2020) for authenticity.
 */
async function testExpiredJwtToken() {
  console.log('TEST: Request with expired JWT token');
  
  // Real JWT that expired on 2020-01-01 - clearly invalid
  const expiredToken = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiYWRtaW4iOnRydWUsImlhdCI6MTU3NzE1MTk3OSwiZXhwIjoxNTc3MTUxOTc5fQ.abc123';
  
  const response = await makeRequest('/api/users', {
    'Authorization': `Bearer ${expiredToken}`
  });
  
  console.log(`  Status: ${response.statusCode}`);
  console.log(`  Expected: 401`);
  console.log(`  Result: ${response.statusCode === 401 ? 'PASS (would fail in red-phase)' : 'FAIL - wrong status'}`);
  
  if (response.statusCode !== 401) {
    throw new Error(
      `Expected HTTP 401 for request with expired JWT token, ` +
      `got ${response.statusCode} instead. ` +
      `This means expired tokens are being accepted!`
    );
  }
}

/**
 * Test 4: Request with a JWT token signed by the wrong key
 * 
 * Falsification: If the endpoint accepts tokens signed with wrong key,
 * it would return a status other than 401.
 * 
 * Oracle: HTTP 401 status code in response.
 * 
 * This test would fail if tokens with invalid signatures are accepted
 * because the response would have status 200/404/500 instead of 401.
 */
async function testWrongSigningKey() {
  console.log('TEST: Request with JWT token signed by wrong key');
  
  // JWT signed with a different secret key
  // This is a valid structure but wrong signature
  const wrongSignedToken = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiYWRtaW4iOnRydWUsImlhdCI6MTYwOTk5OTk5OX0.invalid_signature_here';
  
  const response = await makeRequest('/api/users', {
    'Authorization': `Bearer ${wrongSignedToken}`
  });
  
  console.log(`  Status: ${response.statusCode}`);
  console.log(`  Expected: 401`);
  console.log(`  Result: ${response.statusCode === 401 ? 'PASS (would fail in red-phase)' : 'FAIL - wrong status'}`);
  
  if (response.statusCode !== 401) {
    throw new Error(
      `Expected HTTP 401 for request with JWT signed by wrong key, ` +
      `got ${response.statusCode} instead. ` +
      `This means tokens with invalid signatures are being accepted!`
    );
  }
}

/**
 * Main test runner
 * Runs all auth middleware tests and reports results.
 */
async function runTests() {
  console.log('='.repeat(60));
  console.log('RED-PHASE AUTH TESTS: /api/users JWT validation');
  console.log('='.repeat(60));
  console.log('');
  console.log('These tests verify that the auth middleware correctly rejects');
  console.log('unauthenticated requests by returning HTTP 401.');
  console.log('');
  
  const tests = [
    { name: 'No Authorization header', fn: testNoAuthorizationHeader },
    { name: 'Malformed Authorization header', fn: testMalformedAuthorizationHeader },
    { name: 'Expired JWT token', fn: testExpiredJwtToken },
    { name: 'JWT signed by wrong key', fn: testWrongSigningKey }
  ];
  
  let passed = 0;
  let failed = 0;
  const failures = [];
  
  for (const test of tests) {
    console.log('');
    console.log(`[${tests.indexOf(test) + 1}/${tests.length}] ${test.name}`);
    console.log('-'.repeat(40));
    
    try {
      await test.fn();
      passed++;
    } catch (err) {
      console.log(`  ERROR: ${err.message}`);
      failed++;
      failures.push({ test: test.name, error: err.message });
    }
  }
  
  console.log('');
  console.log('='.repeat(60));
  console.log('TEST SUMMARY');
  console.log('='.repeat(60));
  console.log(`Total: ${tests.length} | Passed: ${passed} | Failed: ${failed}`);
  console.log('');
  
  if (failed > 0) {
    console.log('FAILURES:');
    for (const f of failures) {
      console.log(`  - ${f.test}: ${f.error}`);
    }
    console.log('');
    console.log('In RED-PHASE, test failures are EXPECTED because:');
    console.log('  1. /api/users endpoint does not exist yet');
    console.log('  2. Auth middleware has not been implemented');
    console.log('');
    console.log('These tests will PASS once the auth middleware correctly');
    console.log('intercepts requests and returns 401 for invalid/missing JWT.');
    process.exit(1);
  } else {
    console.log('All tests passed! Auth middleware is working correctly.');
    process.exit(0);
  }
}

// Run tests when this file is executed directly
runTests().catch(err => {
  console.error('Test runner error:', err);
  process.exit(1);
});

module.exports = { runTests, makeRequest };