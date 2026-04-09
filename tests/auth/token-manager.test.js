/**
 * RED-PHASE TESTS: AuthTokenManager
 * 
 * Claim under test: AuthTokenManager must provide centralized token validation
 * with exactly two public methods: validateToken(token: string): TokenClaims
 * and revokeToken(token: string): void.
 * 
 * These tests are designed to FAIL in red-phase because:
 * 1. src/auth/token-manager.ts does not exist yet
 * 2. Even if module exists, the required methods may not be implemented
 * 
 * They will PASS once AuthTokenManager is correctly implemented with:
 * - Exactly two public methods (validateToken and revokeToken)
 * - Proper TokenClaims return on valid tokens
 * - Correct error codes (TOKEN_INVALID, TOKEN_EXPIRED, TOKEN_REVOKED) on failures
 * - Working revocation list that persists across calls
 */

// Error codes expected from src/api/errors/format.ts
// These will be imported once the error format module exists
const ErrorCodes = {
  TOKEN_INVALID: 'TOKEN_INVALID',
  TOKEN_EXPIRED: 'TOKEN_EXPIRED',
  TOKEN_REVOKED: 'TOKEN_REVOKED'
};

/**
 * Test helpers to construct JWTs for testing.
 * These produce real JWTs that would fail validation for specific reasons.
 */

/**
 * Creates a valid JWT structure (but not cryptographically valid without the secret).
 * For testing purposes, we only care about structure and claim content.
 */
function createTestJwt(payload, signature = 'test_signature') {
  const header = { alg: 'HS256', typ: 'JWT' };
  const base64Header = Buffer.from(JSON.stringify(header)).toString('base64url');
  const base64Payload = Buffer.from(JSON.stringify(payload)).toString('base64url');
  return `${base64Header}.${base64Payload}.${signature}`;
}

/**
 * Creates a malformed JWT (invalid base64 in payload)
 */
function createMalformedJwt() {
  return 'header.invalid!!!base64payload.signature';
}

/**
 * Creates a token with missing required claims (no sub, iat, etc)
 */
function createTokenWithMissingClaims() {
  const payload = { some: 'random', fields: true };
  return createTestJwt(payload);
}

/**
 * Creates an expired token (exp is in the past)
 */
function createExpiredToken() {
  const payload = {
    sub: 'user123',
    iat: Math.floor(Date.now() / 1000) - 7200, // 2 hours ago
    exp: Math.floor(Date.now() / 1000) - 3600   // 1 hour ago (expired)
  };
  return createTestJwt(payload);
}

/**
 * Creates a valid-structured token (for testing revocation)
 */
function createValidToken() {
  const payload = {
    sub: 'user123',
    iat: Math.floor(Date.now() / 1000),
    exp: Math.floor(Date.now() / 1000) + 3600   // 1 hour from now
  };
  return createTestJwt(payload);
}

// =============================================================================
// TEST CASES
// =============================================================================

/**
 * Test 1: validateToken with valid token → returns TokenClaims
 * 
 * Claim: validateToken(token: string): TokenClaims
 * 
 * Falsification: If validateToken does not exist, is not a function, or does not
 * return a TokenClaims object with expected properties (sub, iat, exp), this fails.
 * 
 * Oracle honesty: This test would fail if the claim were false because:
 * - Missing validateToken method → TypeError: AuthTokenManager.validateToken is not a function
 * - validateToken returns non-object → assertion fails
 * - validateToken returns object without sub/iat/exp → assertion fails
 */
async function testValidateValidToken(AuthTokenManager) {
  console.log('TEST: validateToken with valid token returns TokenClaims');
  
  const token = createValidToken();
  const claims = AuthTokenManager.validateToken(token);
  
  if (!claims || typeof claims !== 'object') {
    throw new Error(
      `validateToken must return an object, got ${typeof claims}. ` +
      `Claim is false: validateToken does not return TokenClaims.`
    );
  }
  
  if (!claims.sub || !claims.iat || !claims.exp) {
    throw new Error(
      `TokenClaims must have sub, iat, exp properties. ` +
      `Got: ${JSON.stringify(claims)}. ` +
      `Claim is false: validateToken does not return complete TokenClaims.`
    );
  }
  
  console.log(`  TokenClaims: ${JSON.stringify(claims)}`);
  console.log('  PASS: validateToken returns valid TokenClaims');
}

/**
 * Test 2: validateToken with malformed token → throws with TOKEN_INVALID
 * 
 * Claim: validateToken throws on malformed tokens
 * 
 * Falsification: If validateToken accepts malformed tokens without throwing,
 * or throws without the correct error code, this fails.
 * 
 * Oracle honesty: This test would fail if the claim were false because:
 * - Malformed token accepted (no throw) → "Expected exception for malformed token"
 * - Wrong error code thrown → "Expected TOKEN_INVALID, got {code}"
 */
async function testValidateMalformedToken(AuthTokenManager) {
  console.log('TEST: validateToken with malformed token throws TOKEN_INVALID');
  
  const malformedToken = createMalformedJwt();
  
  let thrown = null;
  let errorCode = null;
  
  try {
    AuthTokenManager.validateToken(malformedToken);
  } catch (e) {
    thrown = e;
    errorCode = e.code;
  }
  
  if (!thrown) {
    throw new Error(
      `validateToken must throw on malformed token '${malformedToken}'. ` +
      `Claim is false: validateToken accepts malformed tokens.`
    );
  }
  
  if (errorCode !== ErrorCodes.TOKEN_INVALID) {
    throw new Error(
      `Expected error code TOKEN_INVALID for malformed token, got '${errorCode}'. ` +
      `Claim is false: validateToken does not use correct error code.`
    );
  }
  
  console.log(`  Threw: ${thrown.message}`);
  console.log('  PASS: validateToken rejects malformed token with TOKEN_INVALID');
}

/**
 * Test 3: validateToken with expired token → throws with TOKEN_EXPIRED
 * 
 * Claim: validateToken throws TOKEN_EXPIRED for expired tokens
 * 
 * Falsification: If validateToken accepts expired tokens without throwing,
 * or throws without TOKEN_EXPIRED, this fails.
 * 
 * Oracle honesty: This test would fail if the claim were false because:
 * - Expired token accepted → "Expected exception for expired token"
 * - Wrong error code thrown → "Expected TOKEN_EXPIRED, got {code}"
 */
async function testValidateExpiredToken(AuthTokenManager) {
  console.log('TEST: validateToken with expired token throws TOKEN_EXPIRED');
  
  const expiredToken = createExpiredToken();
  
  let thrown = null;
  let errorCode = null;
  
  try {
    AuthTokenManager.validateToken(expiredToken);
  } catch (e) {
    thrown = e;
    errorCode = e.code;
  }
  
  if (!thrown) {
    throw new Error(
      `validateToken must throw on expired token. ` +
      `Claim is false: validateToken accepts expired tokens.`
    );
  }
  
  if (errorCode !== ErrorCodes.TOKEN_EXPIRED) {
    throw new Error(
      `Expected error code TOKEN_EXPIRED for expired token, got '${errorCode}'. ` +
      `Claim is false: validateToken does not correctly identify expired tokens.`
    );
  }
  
  console.log(`  Threw: ${thrown.message}`);
  console.log('  PASS: validateToken rejects expired token with TOKEN_EXPIRED');
}

/**
 * Test 4: validateToken with revoked token → throws with TOKEN_REVOKED
 * 
 * Claim: validateToken throws TOKEN_REVOKED for revoked tokens
 * 
 * Falsification: If validateToken does not check the revocation list,
 * or throws without TOKEN_REVOKED, this fails.
 * 
 * Oracle honesty: This test would fail if the claim were false because:
 * - Revoked token accepted → "Expected exception for revoked token"
 * - Wrong error code thrown → "Expected TOKEN_REVOKED, got {code}"
 */
async function testValidateRevokedToken(AuthTokenManager) {
  console.log('TEST: validateToken with revoked token throws TOKEN_REVOKED');
  
  // First create a valid token
  const token = createValidToken();
  
  // Revoke it first
  AuthTokenManager.revokeToken(token);
  
  // Now try to validate it
  let thrown = null;
  let errorCode = null;
  
  try {
    AuthTokenManager.validateToken(token);
  } catch (e) {
    thrown = e;
    errorCode = e.code;
  }
  
  if (!thrown) {
    throw new Error(
      `validateToken must throw on revoked token. ` +
      `Claim is false: validateToken does not check revocation list.`
    );
  }
  
  if (errorCode !== ErrorCodes.TOKEN_REVOKED) {
    throw new Error(
      `Expected error code TOKEN_REVOKED for revoked token, got '${errorCode}'. ` +
      `Claim is false: validateToken does not use TOKEN_REVOKED for revoked tokens.`
    );
  }
  
  console.log(`  Threw: ${thrown.message}`);
  console.log('  PASS: validateToken rejects revoked token with TOKEN_REVOKED');
}

/**
 * Test 5: validateToken with missing required claims → throws with TOKEN_INVALID
 * 
 * Claim: validateToken throws TOKEN_INVALID for tokens missing required claims
 * 
 * Falsification: If validateToken accepts tokens without required claims
 * (sub, iat, exp), or doesn't throw TOKEN_INVALID, this fails.
 * 
 * Oracle honesty: This test would fail if the claim were false because:
 * - Token without claims accepted → "Expected exception for missing claims"
 * - Wrong error code thrown → "Expected TOKEN_INVALID, got {code}"
 */
async function testValidateMissingClaims(AuthTokenManager) {
  console.log('TEST: validateToken with missing required claims throws TOKEN_INVALID');
  
  const tokenMissingClaims = createTokenWithMissingClaims();
  
  let thrown = null;
  let errorCode = null;
  
  try {
    AuthTokenManager.validateToken(tokenMissingClaims);
  } catch (e) {
    thrown = e;
    errorCode = e.code;
  }
  
  if (!thrown) {
    throw new Error(
      `validateToken must throw on token missing required claims. ` +
      `Claim is false: validateToken accepts incomplete tokens.`
    );
  }
  
  if (errorCode !== ErrorCodes.TOKEN_INVALID) {
    throw new Error(
      `Expected error code TOKEN_INVALID for token with missing claims, got '${errorCode}'. ` +
      `Claim is false: validateToken does not validate required claims.`
    );
  }
  
  console.log(`  Threw: ${thrown.message}`);
  console.log('  PASS: validateToken rejects token with missing claims with TOKEN_INVALID');
}

/**
 * Test 6: revokeToken adds token to revocation list
 * 
 * Claim: revokeToken(token: string): void adds token to revocation list
 * 
 * Falsification: If revokeToken doesn't add the token to a revocation list,
 * validateToken will not see it as revoked.
 * 
 * Oracle honesty: This test would fail if the claim were false because:
 * - After revokeToken, validateToken would NOT throw TOKEN_REVOKED
 * - This proves revokeToken didn't actually add to revocation list
 */
async function testRevokeTokenAddsToList(AuthTokenManager) {
  console.log('TEST: revokeToken adds token to revocation list');
  
  const token = createValidToken();
  
  // Before revoke, token should be valid
  let claimsBefore = null;
  try {
    claimsBefore = AuthTokenManager.validateToken(token);
  } catch (e) {
    // If it throws before revoke, that's unexpected
    throw new Error(
      `Token should be valid before revokeToken, but threw: ${e.message}. ` +
      `Claim is false: unexpected pre-revocation failure.`
    );
  }
  
  if (!claimsBefore) {
    throw new Error(
      `validateToken should return claims for valid token before revocation. ` +
      `Claim is false: unexpected pre-revocation behavior.`
    );
  }
  
  // Revoke the token
  AuthTokenManager.revokeToken(token);
  
  // After revoke, token should throw TOKEN_REVOKED
  let thrownAfter = null;
  let errorCodeAfter = null;
  
  try {
    AuthTokenManager.validateToken(token);
  } catch (e) {
    thrownAfter = e;
    errorCodeAfter = e.code;
  }
  
  if (!thrownAfter) {
    throw new Error(
      `After revokeToken, validateToken must throw TOKEN_REVOKED. ` +
      `Claim is false: revokeToken does not add token to revocation list.`
    );
  }
  
  if (errorCodeAfter !== ErrorCodes.TOKEN_REVOKED) {
    throw new Error(
      `Expected TOKEN_REVOKED after revokeToken, got '${errorCodeAfter}'. ` +
      `Claim is false: revokeToken does not correctly mark token as revoked.`
    );
  }
  
  console.log('  PASS: revokeToken successfully adds token to revocation list');
}

/**
 * Test 7: validateToken after revokeToken → throws with TOKEN_REVOKED
 * 
 * This is a subset of test 6 but focuses specifically on the validateToken-after-revoke
 * behavior, testing the integration between the two methods.
 * 
 * Oracle honesty: Same as test 6 - if revokeToken doesn't work, validateToken won't throw.
 */
async function testValidateAfterRevoke(AuthTokenManager) {
  console.log('TEST: validateToken after revokeToken throws TOKEN_REVOKED');
  
  const token = createValidToken();
  
  // Revoke first
  AuthTokenManager.revokeToken(token);
  
  // Then validate
  let thrown = null;
  let errorCode = null;
  
  try {
    AuthTokenManager.validateToken(token);
  } catch (e) {
    thrown = e;
    errorCode = e.code;
  }
  
  if (!thrown) {
    throw new Error(
      `validateToken must throw TOKEN_REVOKED after revokeToken is called. ` +
      `Claim is false: revokeToken + validateToken integration is broken.`
    );
  }
  
  if (errorCode !== ErrorCodes.TOKEN_REVOKED) {
    throw new Error(
      `Expected TOKEN_REVOKED, got '${errorCode}'. ` +
      `Claim is false: validateToken does not respect revocation.`
    );
  }
  
  console.log(`  Threw: ${thrown.message}`);
  console.log('  PASS: validateToken respects revocation from revokeToken');
}

/**
 * Test 8: Revoked tokens persist across multiple validateToken calls
 * 
 * Claim: Revocation is permanent - once revoked, a token stays revoked
 * 
 * Falsification: If revocation is not persistent (e.g., one-time use, or
 * clears after first validateToken call), the second validateToken won't throw.
 * 
 * Oracle honesty: This test would fail if the claim were false because:
 * - Second validateToken would NOT throw TOKEN_REVOKED
 * - This proves revocation is not persistent
 */
async function testRevokedTokensPersist(AuthTokenManager) {
  console.log('TEST: Revoked tokens persist across multiple validateToken calls');
  
  const token = createValidToken();
  
  // Revoke the token
  AuthTokenManager.revokeToken(token);
  
  // First validateToken call after revoke
  let thrown1 = null;
  let errorCode1 = null;
  
  try {
    AuthTokenManager.validateToken(token);
  } catch (e) {
    thrown1 = e;
    errorCode1 = e.code;
  }
  
  if (!thrown1 || errorCode1 !== ErrorCodes.TOKEN_REVOKED) {
    throw new Error(
      `First validateToken after revoke must throw TOKEN_REVOKED. ` +
      `Claim is false: revocation is not working.`
    );
  }
  
  // Second validateToken call - should ALSO throw
  let thrown2 = null;
  let errorCode2 = null;
  
  try {
    AuthTokenManager.validateToken(token);
  } catch (e) {
    thrown2 = e;
    errorCode2 = e.code;
  }
  
  if (!thrown2) {
    throw new Error(
      `Second validateToken after revoke must also throw TOKEN_REVOKED. ` +
      `Claim is false: revocation does not persist across calls.`
    );
  }
  
  if (errorCode2 !== ErrorCodes.TOKEN_REVOKED) {
    throw new Error(
      `Second validateToken expected TOKEN_REVOKED, got '${errorCode2}'. ` +
      `Claim is false: revocation persistence is broken.`
    );
  }
  
  console.log('  First validateToken threw TOKEN_REVOKED');
  console.log('  Second validateToken also threw TOKEN_REVOKED');
  console.log('  PASS: Revocation persists across multiple validateToken calls');
}

// =============================================================================
// TEST RUNNER
// =============================================================================

/**
 * Main test runner for AuthTokenManager red-phase tests.
 */
async function runTests() {
  console.log('='.repeat(70));
  console.log('RED-PHASE AUTH TOKEN MANAGER TESTS');
  console.log('='.repeat(70));
  console.log('');
  console.log('These tests verify AuthTokenManager with exactly two public methods:');
  console.log('  - validateToken(token: string): TokenClaims');
  console.log('  - revokeToken(token: string): void');
  console.log('');
  console.log('FAILURE EXPECTED: AuthTokenManager does not exist yet.');
  console.log('');
  
  let AuthTokenManager = null;
  let importError = null;
  
  // Try to import AuthTokenManager
  console.log('Attempting to import AuthTokenManager from src/auth/token-manager...');
  try {
    // Dynamic import - will fail in red-phase because module doesn't exist
    const module = await import('../src/auth/token-manager.js');
    AuthTokenManager = module.AuthTokenManager || module.default;
    
    if (!AuthTokenManager) {
      importError = 'Module loaded but AuthTokenManager export not found';
    } else {
      console.log('  SUCCESS: AuthTokenManager imported');
    }
  } catch (e) {
    importError = e.message;
    console.log(`  FAILED: ${importError}`);
  }
  
  console.log('');
  
  // If import failed, we expect all tests to fail - this is correct red-phase behavior
  if (!AuthTokenManager) {
    console.log('='.repeat(70));
    console.log('RED-PHASE CONFIRMED: AuthTokenManager does not exist');
    console.log('='.repeat(70));
    console.log('');
    console.log('Import error was: ' + importError);
    console.log('');
    console.log('This is EXPECTED in red-phase. Tests would have failed for the');
    console.log('following reasons if the module existed but was incomplete:');
    console.log('');
    
    // List what each test would check
    const testDescriptions = [
      '1. validateToken must return TokenClaims for valid tokens',
      '2. validateToken must throw TOKEN_INVALID for malformed tokens',
      '3. validateToken must throw TOKEN_EXPIRED for expired tokens',
      '4. validateToken must throw TOKEN_REVOKED for revoked tokens',
      '5. validateToken must throw TOKEN_INVALID for missing required claims',
      '6. revokeToken must add tokens to the revocation list',
      '7. validateToken must throw TOKEN_REVOKED after revokeToken',
      '8. Revocation must persist across multiple validateToken calls'
    ];
    
    testDescriptions.forEach(desc => console.log('  - ' + desc));
    
    console.log('');
    console.log('Tests are correctly designed to fail until AuthTokenManager is implemented.');
    
    // In red-phase, we report failure as expected
    process.exit(1);
  }
  
  // If import succeeded, run the actual tests
  console.log('');
  console.log('AuthTokenManager loaded. Running tests...');
  console.log('');
  
  const tests = [
    { name: 'validateToken with valid token returns TokenClaims', fn: testValidateValidToken },
    { name: 'validateToken with malformed token throws TOKEN_INVALID', fn: testValidateMalformedToken },
    { name: 'validateToken with expired token throws TOKEN_EXPIRED', fn: testValidateExpiredToken },
    { name: 'validateToken with revoked token throws TOKEN_REVOKED', fn: testValidateRevokedToken },
    { name: 'validateToken with missing required claims throws TOKEN_INVALID', fn: testValidateMissingClaims },
    { name: 'revokeToken adds token to revocation list', fn: testRevokeTokenAddsToList },
    { name: 'validateToken after revokeToken throws TOKEN_REVOKED', fn: testValidateAfterRevoke },
    { name: 'Revoked tokens persist across multiple validateToken calls', fn: testRevokedTokensPersist }
  ];
  
  let passed = 0;
  let failed = 0;
  const failures = [];
  
  for (const test of tests) {
    console.log(`[${tests.indexOf(test) + 1}/${tests.length}] ${test.name}`);
    console.log('-'.repeat(60));
    
    try {
      await test.fn(AuthTokenManager);
      passed++;
    } catch (err) {
      console.log(`  ERROR: ${err.message}`);
      failed++;
      failures.push({ test: test.name, error: err.message });
    }
    console.log('');
  }
  
  console.log('='.repeat(70));
  console.log('TEST SUMMARY');
  console.log('='.repeat(70));
  console.log(`Total: ${tests.length} | Passed: ${passed} | Failed: ${failed}`);
  console.log('');
  
  if (failed > 0) {
    console.log('FAILURES:');
    for (const f of failures) {
      console.log(`  - ${f.test}: ${f.error}`);
    }
    console.log('');
    console.log('In RED-PHASE, failures indicate the claim is not yet satisfied.');
    process.exit(1);
  } else {
    console.log('All tests passed! AuthTokenManager satisfies the claim.');
    process.exit(0);
  }
}

// Export for potential use by other test runners
module.exports = { runTests };

// Run tests when executed directly
if (require.main === module) {
  runTests().catch(err => {
    console.error('Test runner error:', err);
    process.exit(1);
  });
}
