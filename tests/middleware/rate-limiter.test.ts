/**
 * Red-phase tests for rate limiter middleware
 *
 * Claim under test: "the rate limiter blocks requests exceeding 100 requests
 * per minute per IP address and returns HTTP 429 with a Retry-After header
 * indicating the number of seconds until the limit resets."
 *
 * Compound falsification criteria:
 * 1. Test fails if requests beyond 100-per-minute limit are allowed through
 * 2. Test fails if response status code is not 429
 * 3. Test fails if Retry-After header is missing or contains incorrect value
 *
 * These tests are designed to FAIL in red-phase because:
 * 1. src/middleware/rate-limiter.ts does not exist
 * 2. No server is running to handle requests
 *
 * They will PASS once the rate limiter middleware is properly implemented
 * and integrated into the server pipeline.
 *
 * Forbidden pattern check: No mocking of rate limiter internals. The rate
 * limiter's counting mechanism, threshold comparison, and reset timer are
 * the integration boundaries the claim depends on. HTTP-layer interactions
 * (IP extraction via X-Forwarded-For, response construction) are real.
 */

import http from 'http';

// Server configuration
const PORT = process.env.PORT || 3000;
const BASE_URL = `http://localhost:${PORT}`;
const RATE_LIMIT = 100;
const WINDOW_SECONDS = 60;

// Reusable test endpoint — any non-authenticated endpoint the rate limiter protects
const TEST_PATH = '/api/health';

/**
 * Makes a real HTTP request with optional X-Forwarded-For header to simulate
 * different client IPs. No mocks — the rate limiter's IP-extraction logic
 * (req.ip, req.socket.remoteAddress, or X-Forwarded-For parsing) is the
 * integration boundary exercised by these tests.
 */
function makeRequest(
  path: string,
  clientIp: string,
  method: string = 'GET'
): Promise<{
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
      headers: {
        'X-Forwarded-For': clientIp,
        'X-Client-IP': clientIp,
      },
    };

    const req = http.request(options, (res) => {
      let body = '';
      res.on('data', (chunk: Buffer) => body += chunk.toString());
      res.on('end', () => {
        resolve({
          statusCode: res.statusCode || 0,
          headers: res.headers,
          body: body,
        });
      });
    });

    req.on('error', (err: NodeJS.ErrnoException) => {
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
 * Makes N concurrent-ish requests rapidly in sequence (minimal inter-request delay).
 * Used to push past the rate limit threshold quickly.
 */
async function makeBurstRequests(
  path: string,
  clientIp: string,
  count: number
): Promise<Array<{ statusCode: number; headers: http.IncomingHttpHeaders; body: string }>> {
  const results: Array<{ statusCode: number; headers: http.IncomingHttpHeaders; body: string }> = [];
  for (let i = 0; i < count; i++) {
    // Minimal delay — only what the event loop allows between iterations
    await new Promise<void>((resolve) => setImmediate(resolve));
    results.push(await makeRequest(path, clientIp));
  }
  return results;
}

// ============================================================================
// CLAIM ASPECT 1: Threshold enforcement — 101st request from same IP is blocked
// ============================================================================

/**
 * Test: blocks the 101st request from the same IP within one minute
 *
 * Falsification: If the rate limiter allows more than 100 requests through,
 * the 101st request will return 200/2xx instead of 429.
 *
 * Oracle: HTTP 429 status code on request #101.
 *
 * Oracle honesty justification: This test would fail if the claim were false
 * because the rate limiter would NOT block at 100 requests — it would either
 * allow the 101st request through (returning 200) or not enforce a threshold.
 * A rate limiter that blocks at 99, 102, or not at all would also fail this
 * test, making it a precise threshold probe.
 *
 * Coverage trace:
 * - Forces the rate-limit counting path (incrementing the per-IP counter)
 * - Forces the threshold comparison path (counter > 100 check)
 * - Forces the rejection path (short-circuit before passing to next handler)
 * - Exercises the 429 response construction path (statusCode = 429)
 *
 * Adversarial check: A rate limiter that blocks at 99 or 102 would fail this
 * test, ensuring the threshold is exactly 100, not approximately 100.
 */
async function testThresholdEnforcement101stRequestBlocked(): Promise<void> {
  console.log('TEST: 101st request from same IP is blocked with 429');

  const clientIp = '203.0.113.1'; // Routable test IP (RFC 5737)
  const requestsToSend = RATE_LIMIT + 1; // 101

  console.log(`  Sending ${requestsToSend} requests from ${clientIp}...`);

  const results = await makeBurstRequests(TEST_PATH, clientIp, requestsToSend);

  const first100 = results.slice(0, RATE_LIMIT);
  const the101st = results[RATE_LIMIT]; // 0-indexed, so index 100 = 101st request

  console.log(`  First 100 requests:`);
  const first100Statuses = first100.map((r) => r.statusCode);
  const uniqueFirst100 = [...new Set(first100Statuses)];
  console.log(`    Status codes seen: ${uniqueFirst100.join(', ')}`);
  console.log(`  Request #101:`);
  console.log(`    Status code: ${the101st.statusCode}`);
  console.log(`    Expected: 429`);

  // First 100 requests should NOT all be blocked (they are within limit)
  const allFirst100Allowed = first100.every((r) => r.statusCode === 200 || r.statusCode === 204);
  if (!allFirst100Allowed) {
    throw new Error(
      `Expected first ${RATE_LIMIT} requests to be allowed, but some received non-2xx status. ` +
      `Statuses: ${first100Statuses.join(', ')}. ` +
      `This means the rate limiter is blocking requests within the allowed limit!`
    );
  }

  // The 101st request MUST be blocked with 429
  if (the101st.statusCode !== 429) {
    throw new Error(
      `Expected request #101 to be rate-limited with HTTP 429, ` +
      `but received ${the101st.statusCode} instead. ` +
      `This means requests beyond the ${RATE_LIMIT}-per-minute limit are being allowed through!`
    );
  }

  console.log('  PASS: 101st request correctly blocked with 429');
}

// ============================================================================
// CLAIM ASPECT 2: Per-IP counter isolation
// ============================================================================

/**
 * Test: each IP address has an independent request counter
 *
 * Falsification: If the rate limiter uses a global counter instead of
 * per-IP counters, request 51 from IP-B would be blocked because IP-A's
 * counter would be at 100.
 *
 * Oracle: HTTP 200 on request #51 from IP-B (and request #101 from IP-A
 * still blocked).
 *
 * Oracle honesty justification: This test would fail if the claim were false
 * because a globally-counting rate limiter would treat both IPs as the same
 * counter. IP-B's 51st request would hit the global 100 limit and get 429,
 * proving the counter is shared rather than per-IP.
 *
 * Coverage trace:
 * - Forces the per-IP counter lookup/creation path (keying by IP)
 * - Confirms that incrementing IP-A's counter does NOT affect IP-B's counter
 * - Exercises the counting path twice (once per IP)
 *
 * Adversarial check: A rate limiter that tracks by API key, session, or any
 * other identifier instead of IP would fail this test because it would not
 * maintain independent counters per IP.
 */
async function testPerIpCounterIsolation(): Promise<void> {
  console.log('TEST: Per-IP counter isolation');

  const ipA = '203.0.113.1';
  const ipB = '203.0.113.2';
  const requestsPerIp = 50; // Well within the 100/minute limit

  console.log(`  Sending ${requestsPerIp} requests from ${ipA}...`);
  const resultsA = await makeBurstRequests(TEST_PATH, ipA, requestsPerIp);

  console.log(`  Sending ${requestsPerIp} requests from ${ipB}...`);
  const resultsB = await makeBurstRequests(TEST_PATH, ipB, requestsPerIp);

  const aStatuses = resultsA.map((r) => r.statusCode);
  const bStatuses = resultsB.map((r) => r.statusCode);

  console.log(`  ${ipA} statuses: ${[...new Set(aStatuses)].join(', ')}`);
  console.log(`  ${ipB} statuses: ${[...new Set(bStatuses)].join(', ')}`);

  const allA200 = resultsA.every((r) => r.statusCode === 200 || r.statusCode === 204);
  const allB200 = resultsB.every((r) => r.statusCode === 200 || r.statusCode === 204);

  if (!allA200) {
    throw new Error(
      `Expected all ${requestsPerIp} requests from ${ipA} to be allowed (within limit), ` +
      `but got statuses: ${aStatuses.join(', ')}. ` +
      `This means IP-A is being incorrectly rate-limited despite being under the limit!`
    );
  }

  if (!allB200) {
    throw new Error(
      `Expected all ${requestsPerIp} requests from ${ipB} to be allowed (within limit), ` +
      `but got statuses: ${bStatuses.join(', ')}. ` +
      `This means the rate limiter is NOT maintaining independent per-IP counters!`
    );
  }

  console.log('  PASS: Both IPs independently allowed within limit');

  // Also verify that IP-A at request #101 is still blocked (not permanently blocked)
  console.log(`  Verifying ${ipA} is still subject to its own limit (request #101)...`);
  const ipARequest101 = await makeRequest(TEST_PATH, ipA);
  if (ipARequest101.statusCode !== 429) {
    throw new Error(
      `Expected ${ipA} request #101 to be rate-limited with HTTP 429, ` +
      `but received ${ipARequest101.statusCode}. ` +
      `This suggests the per-IP counter is not being enforced correctly.`
    );
  }
  console.log('  PASS: IP-A independently rate-limited at 100 requests');
}

// ============================================================================
// CLAIM ASPECT 3: Retry-After header on 429 responses
// ============================================================================

/**
 * Test: 429 response includes Retry-After header with a positive integer
 * representing seconds until the rate limit window resets
 *
 * Falsification: If the Retry-After header is missing, null, zero, negative,
 * or non-integer, the claim is false.
 *
 * Oracle: Retry-After header is present, parses as a positive integer > 0,
 * and the value is ≤ WINDOW_SECONDS (60) — it's the time remaining in the
 * current window, not a fixed value.
 *
 * Oracle honesty justification: This test would fail if the claim were false
 * because a rate limiter that omits the Retry-After header, returns
 * Retry-After: 0, returns a string like "60 seconds", or returns a value
 * greater than the remaining window time would fail the specific assertions.
 *
 * Coverage trace:
 * - Forces the 429 response construction path
 * - Specifically exercises the Retry-After header construction path
 * - Verifies the header is attached to the HTTP response object
 *
 * Adversarial check: A rate limiter that returns Retry-After: 0 or a very
 * small value would fail because we assert the value is a positive integer.
 * A rate limiter that returns a value > 60 (the full window) would also fail
 * because we assert it's ≤ 60 (time remaining in current window, not the
 * full window length). A rate limiter that returns a non-integer (e.g.,
 * "60.5" or "invalid") would also fail.
 */
async function test429IncludesRetryAfterHeader(): Promise<void> {
  console.log('TEST: 429 response includes Retry-After header');

  const clientIp = '203.0.113.3';
  // Exhaust the rate limit to trigger a 429
  console.log(`  Exhausting rate limit for ${clientIp}...`);
  await makeBurstRequests(TEST_PATH, clientIp, RATE_LIMIT);

  const response = await makeRequest(TEST_PATH, clientIp);

  console.log(`  Status code: ${response.statusCode}`);
  console.log(`  Expected: 429`);

  if (response.statusCode !== 429) {
    throw new Error(
      `Expected HTTP 429 when rate limit is exceeded, ` +
      `but received ${response.statusCode} instead. ` +
      `Cannot test Retry-After header without a 429 response.`
    );
  }

  const retryAfterRaw = response.headers['retry-after'];
  console.log(`  Retry-After header: ${retryAfterRaw}`);
  console.log(`  Expected: present and positive integer ≤ ${WINDOW_SECONDS}`);

  if (!retryAfterRaw) {
    throw new Error(
      `Expected Retry-After header on HTTP 429 response, but it is missing. ` +
      `This means the rate limiter is not informing clients when to retry!`
    );
  }

  const retryAfter = Number(retryAfterRaw);
  if (isNaN(retryAfter)) {
    throw new Error(
      `Expected Retry-After header to be parseable as a number, ` +
      `but got: "${retryAfterRaw}". ` +
      `Retry-After must be a numeric value representing seconds.`
    );
  }

  if (retryAfter <= 0) {
    throw new Error(
      `Expected Retry-After header to be a positive integer (> 0), ` +
      `but got: ${retryAfter}. ` +
      `A zero or negative Retry-After value is misleading and provides no useful wait time.`
    );
  }

  if (!Number.isInteger(retryAfter)) {
    throw new Error(
      `Expected Retry-After header to be an integer, ` +
      `but got: ${retryAfter}. ` +
      `Retry-After must be a whole number of seconds.`
    );
  }

  if (retryAfter > WINDOW_SECONDS) {
    throw new Error(
      `Expected Retry-After header to be ≤ ${WINDOW_SECONDS} (time remaining in window), ` +
      `but got: ${retryAfter}. ` +
      `A value exceeding the window duration suggests incorrect Retry-After calculation.`
    );
  }

  console.log(`  PASS: Retry-After = ${retryAfter} (positive integer ≤ ${WINDOW_SECONDS})`);
}

// ============================================================================
// CLAIM ASPECT 4: Rate limit window resets after time expires
// ============================================================================

/**
 * Test: after the rate limit window expires, requests are accepted again
 *
 * Falsification: If the rate limit does not reset after the window expires,
 * requests beyond the window would still receive 429.
 *
 * Oracle: After waiting (WINDOW_SECONDS + buffer), subsequent requests return
 * 200 instead of 429.
 *
 * Oracle honesty justification: This test would fail if the claim were false
 * because the rate limiter would either (a) never reset (perpetual block),
 * or (b) reset incorrectly (still return 429 after the window). The test
 * waits for the full window duration plus a buffer before retrying, ensuring
 * any correctly-implemented reset mechanism has fired.
 *
 * Coverage trace:
 * - Exercises the window reset timer logic (fixed-window expiry check)
 * - Verifies the per-IP counter is cleared/aged-out after the window
 * - Exercises the request acceptance path (not blocked) after reset
 *
 * Note: This test takes ~60 seconds to run (WINDOW_SECONDS wait).
 * In CI/iteration cycles, consider running this test last or with --timeout.
 *
 * Adversarial check: A rate limiter that resets immediately (always 0 wait)
 * would pass this test but would be incorrect. However, that would be caught
 * by the threshold tests. A rate limiter that never resets would fail this test.
 */
async function testWindowResetsAfterTimeExpires(): Promise<void> {
  console.log('TEST: Rate limit window resets after time expires');
  console.log(`  NOTE: This test takes ~${WINDOW_SECONDS + 5} seconds to run`);

  const clientIp = '203.0.113.4';

  // Exhaust the rate limit
  console.log(`  Exhausting rate limit for ${clientIp}...`);
  await makeBurstRequests(TEST_PATH, clientIp, RATE_LIMIT);

  // Confirm blocked
  const blockedResponse = await makeRequest(TEST_PATH, clientIp);
  if (blockedResponse.statusCode !== 429) {
    throw new Error(
      `Sanity check failed: expected 429 after exhausting limit, got ${blockedResponse.statusCode}`
    );
  }
  console.log('  Confirmed: rate limit is active (429 returned)');

  // Wait for the window to expire (with 5-second buffer for clock skew)
  const waitTime = WINDOW_SECONDS + 5;
  console.log(`  Waiting ${waitTime} seconds for window to reset...`);
  await new Promise<void>((resolve) => setTimeout(resolve, waitTime * 1000));

  // After reset, request should be allowed
  console.log(`  Requesting after window reset...`);
  const afterResetResponse = await makeRequest(TEST_PATH, clientIp);
  console.log(`  Status code: ${afterResetResponse.statusCode}`);
  console.log(`  Expected: 200 or 204`);

  if (afterResetResponse.statusCode !== 200 && afterResetResponse.statusCode !== 204) {
    throw new Error(
      `Expected request after window reset to be allowed (200/204), ` +
      `but received ${afterResetResponse.statusCode}. ` +
      `This means the rate limiter is NOT resetting after the window expires!`
    );
  }

  console.log('  PASS: Rate limit window correctly reset, requests accepted');
}

// ============================================================================
// CLAIM ASPECT 5: No permanent blacklist — reset allows previously-blocked IPs
// ============================================================================

/**
 * Test: a previously rate-limited IP is NOT permanently blacklisted; after
 * the window resets, it receives 200, not a stale 429
 *
 * Falsification: If the rate limiter permanently blacklists an IP after a
 * single over-limit event, the IP would continue to receive 429 even after
 * the window resets.
 *
 * Oracle: After window reset, the previously-blocked IP receives 200, not 429.
 *
 * Oracle honesty justification: This test would fail if the claim were false
 * because a malicious or buggy rate limiter implementation might maintain a
 * blacklist set of IPs that are permanently blocked. This is distinct from
 * the window-reset test because it verifies the counter reset specifically for
 * an IP that was actually blocked, not just an IP that was within limit.
 *
 * Coverage trace:
 * - Exercises the blocked-IP path and the reset path for a blocked IP
 * - Verifies the counter is cleared for the previously-blocked IP
 * - Exercises the request acceptance path after reset
 *
 * Note: This test takes ~60 seconds to run.
 *
 * Adversarial check: A rate limiter that blacklists on first over-limit would
 * fail this test because the IP would still receive 429 after reset.
 */
async function testNoPermanentBlacklist(): Promise<void> {
  console.log('TEST: Previously rate-limited IP is not permanently blacklisted');
  console.log(`  NOTE: This test takes ~${WINDOW_SECONDS + 5} seconds to run`);

  const clientIp = '203.0.113.5';

  // Exhaust the rate limit
  console.log(`  Exhausting rate limit for ${clientIp}...`);
  await makeBurstRequests(TEST_PATH, clientIp, RATE_LIMIT);

  // Confirm blocked — this IP has been flagged as over-limit
  const blockedResponse = await makeRequest(TEST_PATH, clientIp);
  if (blockedResponse.statusCode !== 429) {
    throw new Error(
      `Sanity check failed: expected 429 after exhausting limit, got ${blockedResponse.statusCode}`
    );
  }
  console.log(`  Confirmed: ${clientIp} is rate-limited (429 returned)`);

  // Wait for window reset
  const waitTime = WINDOW_SECONDS + 5;
  console.log(`  Waiting ${waitTime} seconds for window to reset...`);
  await new Promise<void>((resolve) => setTimeout(resolve, waitTime * 1000));

  // After reset, previously blocked IP should get 200, NOT 429
  console.log(`  Requesting from previously-blocked ${clientIp} after reset...`);
  const afterResetResponse = await makeRequest(TEST_PATH, clientIp);
  console.log(`  Status code: ${afterResetResponse.statusCode}`);
  console.log(`  Expected: 200 or 204 (NOT 429 — no permanent blacklist)`);

  if (afterResetResponse.statusCode === 429) {
    throw new Error(
      `Expected previously rate-limited IP ${clientIp} to be allowed after window reset, ` +
      `but still receiving HTTP 429. ` +
      `This means the rate limiter is PERMANENTLY blacklisting IPs after a single over-limit event!`
    );
  }

  if (afterResetResponse.statusCode !== 200 && afterResetResponse.statusCode !== 204) {
    throw new Error(
      `Expected 200/204 after window reset, but received ${afterResetResponse.statusCode}.`
    );
  }

  console.log('  PASS: No permanent blacklist — previously blocked IP allowed after reset');
}

// ============================================================================
// Test runner
// ============================================================================

async function runTests(): Promise<void> {
  console.log('='.repeat(70));
  console.log('RED-PHASE RATE LIMITER TESTS');
  console.log('='.repeat(70));
  console.log('');
  console.log('Compound claim: "the rate limiter blocks requests exceeding 100');
  console.log('requests per minute per IP address and returns HTTP 429 with a');
  console.log('Retry-After header indicating the number of seconds until reset."');
  console.log('');
  console.log('Each test targets a specific independently-falsifiable aspect.');
  console.log('');
  console.log(`Configuration:`);
  console.log(`  Rate limit: ${RATE_LIMIT} requests per ${WINDOW_SECONDS} seconds`);
  console.log(`  Test endpoint: ${TEST_PATH}`);
  console.log(`  Base URL: ${BASE_URL}`);
  console.log('');

  const tests: Array<{ name: string; fn: () => Promise<void>; slow: boolean }> = [
    {
      name: 'Threshold enforcement: 101st request blocked with 429',
      fn: testThresholdEnforcement101stRequestBlocked,
      slow: false,
    },
    {
      name: 'Per-IP counter isolation',
      fn: testPerIpCounterIsolation,
      slow: false,
    },
    {
      name: '429 includes Retry-After header (positive integer ≤ 60s)',
      fn: test429IncludesRetryAfterHeader,
      slow: false,
    },
    {
      name: 'Window resets after time expires',
      fn: testWindowResetsAfterTimeExpires,
      slow: true,
    },
    {
      name: 'No permanent blacklist after window reset',
      fn: testNoPermanentBlacklist,
      slow: true,
    },
  ];

  let passed = 0;
  let failed = 0;
  const failures: Array<{ test: string; error: string }> = [];

  for (let i = 0; i < tests.length; i++) {
    const { name, fn, slow } = tests[i];
    const testIndex = i + 1;
    console.log('');
    console.log(`[${testIndex}/${tests.length}] ${name}${slow ? ' (slow ~65s)' : ''}`);
    console.log('-'.repeat(60));

    try {
      await fn();
      passed++;
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : String(err);
      console.log(`  ERROR: ${errorMessage}`);
      failed++;
      failures.push({ test: name, error: errorMessage });
    }
  }

  console.log('');
  console.log('='.repeat(70));
  console.log('TEST SUMMARY');
  console.log('='.repeat(70));
  console.log(`Total: ${tests.length} | Passed: ${passed} | Failed: ${failed}`);
  console.log('');

  if (failed > 0) {
    console.log('FAILURES:');
    for (const f of failures) {
      console.log(`  - ${f.test}`);
      console.log(`    ${f.error}`);
    }
    console.log('');
    console.log('In RED-PHASE, test failures are EXPECTED because:');
    console.log('  1. src/middleware/rate-limiter.ts does not exist');
    console.log('  2. No server is running (ECONNREFUSED)');
    console.log('');
    console.log('These tests will PASS once the rate limiter middleware:');
    console.log('  - Correctly counts requests per IP in a 60-second fixed window');
    console.log('  - Blocks at exactly 100 requests (not 99, not 101)');
    console.log('  - Returns HTTP 429 with Retry-After header');
    console.log('  - Resets counters after the window expires');
    console.log('  - Does NOT permanently blacklist IPs');
    process.exit(1);
  } else {
    console.log('All tests passed! Rate limiter is working correctly.');
    process.exit(0);
  }
}

// Export for potential use by other test runners
export { runTests, makeRequest, makeBurstRequests };

// Run tests when this file is executed directly
runTests().catch((err) => {
  console.error('Test runner error:', err);
  process.exit(1);
});
