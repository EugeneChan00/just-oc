/**
 * Red-phase auth tests for /api/users endpoint
 *
 * Claim under test: the /api/users endpoint returns HTTP 401 for requests
 * that do not include a valid JWT token in the Authorization header.
 *
 * These tests are designed to FAIL in red-phase because:
 * 1. /api/users endpoint does not exist
 * 2. Auth middleware has not been implemented
 *
 * They will PASS once the auth middleware is properly implemented.
 *
 * Forbidden pattern check: No HTTP-layer mocks. All HTTP interactions are real.
 * The auth middleware's interaction with the HTTP request/response cycle is the
 * integration boundary - mocking it would make the test dishonest by construction.
 */

import http from 'http';

// Server configuration - assumes server is running on port 3000
const PORT = process.env.PORT || 3000;
const BASE_URL = `http://localhost:${PORT}`;

/**
 * Makes a real HTTP request to the given path with optional headers.
 * No mocks - all HTTP layer interactions are real.
 * This is the integration boundary the claim depends on.
 */
function makeRequest(path: string, headers: Record<string, string> = {}, method: string = 'GET'): Promise<{
  statusCode: number;
  headers: http.IncomingHttpHeaders;
  body: string;
  error?: string;
}> {
  return new Promise((resolve) => {
    const url = new URL(path, BASE_URL);
    const options: http.RequestOptions = {
      hostname: url.hostname,
      port: url.port,
      path: url.pathname,
      method: method,
      headers: headers
    };

    const req = http.request(options, (res) => {
      let body = '';
      res.on('data', (chunk: Buffer) => body += chunk.toString());
      res.on('end', () => {
        resolve({
          statusCode: res.statusCode || 0,
          headers: res.headers,
          body: body
        });
      });
    });

    req.on('error', (err: NodeJS.ErrnoException) => {
      // Connection refused means server not running - this is expected in red-phase
      if (err.code === 'ECONNREFUSED') {
        resolve({ statusCode: 0, headers: {}, body: '', error: 'SERVER_NOT_RUNNING' });
      } else {
        resolve({ statusCode: 0, headers: {}, body: '', error: err.message });
      }
    });

    req.end();
  });
}

/**
 * Test 1: Request with no Authorization header at all
 *
 * Falsification: If the endpoint accepts unauthenticated requests,
 * it would return a status other than 401 (e.g., 200, 204, 404).
 *
 * Oracle: HTTP 401 status code in response.
 *
 * This test would fail if unauthenticated requests are accepted because
 * the response would have status 200/204/404 instead of 401.
 *
 * Coverage trace: Forces the middleware path where auth header presence is checked.
 * If no Authorization header exists, the middleware must reject with 401.
 */
async function testNoAuthorizationHeader(): Promise<void> {
  console.log('TEST: Request with no Authorization header');

  const response = await makeRequest('/api/users', {});

  console.log(`  Status: ${response.statusCode}`);
  console.log(`  Expected: 401`);

  if (response.statusCode !== 401) {
    throw new Error(
      `Expected HTTP 401 for request without Authorization header, ` +
      `got ${response.statusCode} instead. ` +
      `This means unauthenticated requests are being accepted!`
    );
  }
  console.log('  PASS: Correctly returned 401');
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
 *
 * Coverage trace: Forces the middleware path where token format is validated.
 * The middleware must check for 'Bearer ' prefix and reject without it.
 */
async function testMalformedAuthorizationHeader(): Promise<void> {
  console.log('TEST: Request with malformed Authorization header');

  // Missing 'Bearer ' prefix - just a raw token string
  const response = await makeRequest('/api/users', {
    'Authorization': 'invalid-token-format'
  });

  console.log(`  Status: ${response.statusCode}`);
  console.log(`  Expected: 401`);

  if (response.statusCode !== 401) {
    throw new Error(
      `Expected HTTP 401 for request with malformed Authorization header, ` +
      `got ${response.statusCode} instead. ` +
      `This means malformed tokens are being accepted!`
    );
  }
  console.log('  PASS: Correctly returned 401');
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
 *
 * Coverage trace: Forces the middleware path where JWT expiration is checked.
 * The middleware must decode the JWT, check the 'exp' claim, and reject if expired.
 */
async function testExpiredJwtToken(): Promise<void> {
  console.log('TEST: Request with expired JWT token');

  // Real JWT that expired on 2020-01-01 - clearly invalid
  // Header: {"alg":"HS256","typ":"JWT"}
  // Payload: {"sub":"1234567890","name":"John Doe","admin":true,"iat":1577151979,"exp":1577151979}
  const expiredToken = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiYWRtaW4iOnRydWUsImlhdCI6MTU3NzE1MTk3OSwiZXhwIjoxNTc3MTUxOTc5fQ.abc123';

  const response = await makeRequest('/api/users', {
    'Authorization': `Bearer ${expiredToken}`
  });

  console.log(`  Status: ${response.statusCode}`);
  console.log(`  Expected: 401`);

  if (response.statusCode !== 401) {
    throw new Error(
      `Expected HTTP 401 for request with expired JWT token, ` +
      `got ${response.statusCode} instead. ` +
      `This means expired tokens are being accepted!`
    );
  }
  console.log('  PASS: Correctly returned 401');
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
 *
 * Coverage trace: Forces the middleware path where JWT signature is cryptographically verified.
 * The middleware must verify the signature using the secret key and reject if invalid.
 */
async function testWrongSigningKey(): Promise<void> {
  console.log('TEST: Request with JWT token signed by wrong key');

  // JWT with valid structure but invalid signature
  // This would fail cryptographic verification if the secret doesn't match
  const wrongSignedToken = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiYWRtaW4iOnRydWUsImlhdCI6MTYwOTk5OTk5OX0.invalid_signature_here';

  const response = await makeRequest('/api/users', {
    'Authorization': `Bearer ${wrongSignedToken}`
  });

  console.log(`  Status: ${response.statusCode}`);
  console.log(`  Expected: 401`);

  if (response.statusCode !== 401) {
    throw new Error(
      `Expected HTTP 401 for request with JWT signed by wrong key, ` +
      `got ${response.statusCode} instead. ` +
      `This means tokens with invalid signatures are being accepted!`
    );
  }
  console.log('  PASS: Correctly returned 401');
}

/**
 * Main test runner
 * Runs all auth middleware tests and reports results.
 */
async function runTests(): Promise<void> {
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
  const failures: { test: string; error: string }[] = [];

  for (const test of tests) {
    const testIndex = tests.indexOf(test) + 1;
    console.log('');
    console.log(`[${testIndex}/${tests.length}] ${test.name}`);
    console.log('-'.repeat(40));

    try {
      await test.fn();
      passed++;
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : String(err);
      console.log(`  ERROR: ${errorMessage}`);
      failed++;
      failures.push({ test: test.name, error: errorMessage });
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

// Export for potential use by other test runners
export { runTests, makeRequest };

// Run tests when this file is executed directly
runTests().catch(err => {
  console.error('Test runner error:', err);
  process.exit(1);
});
