/**
 * RED-PHASE TESTS: /api/register endpoint input validation
 *
 * Claim under test: "When the registration endpoint receives invalid input
 * (bad email, weak password, invalid username, age < 13), it must:
 *   1. Return HTTP 400 status
 *   2. Use the formatError(code, message, details?) function to structure
 *      the error response
 *   3. Include specific validation error details for each field"
 *
 * These tests are designed to FAIL in red-phase because:
 *   1. /api/register endpoint does not exist
 *   2. formatError() from src/api/errors/format.ts does not exist
 *   3. src/validation/user-schema.ts does not exist
 *   4. No server is running (ECONNREFUSED expected)
 *
 * They will PASS once:
 *   - /api/register endpoint is implemented
 *   - Input validation rejects invalid fields with HTTP 400
 *   - Error responses use formatError() structure: { code: 400, message: "...", details: {...} }
 *
 * Forbidden pattern check: No HTTP-layer mocks. All HTTP interactions are real.
 * The registration endpoint's validation logic and error response construction
 * are the integration boundary - mocking them would make tests dishonest.
 */

import http from 'http';

// Server configuration - assumes server is running on port 3000
const PORT = process.env.PORT || 3000;
const BASE_URL = `http://localhost:${PORT}`;
const REGISTER_PATH = '/api/register';

/**
 * formatError response structure (from brief):
 * {
 *   code: number,      // HTTP status code (400)
 *   message: string,   // Human-readable error message
 *   details?: object  // Field-level validation errors
 * }
 */
interface FormatErrorResponse {
  code: number;
  message: string;
  details?: Record<string, string>;
}

/**
 * Makes a real HTTP POST request to the registration endpoint.
 * No mocks - all HTTP layer interactions are real.
 * This is the integration boundary the claim depends on.
 */
function makeRegisterRequest(
  body: Record<string, unknown>,
  headers: Record<string, string> = {}
): Promise<{
  statusCode: number;
  headers: http.IncomingHttpHeaders;
  body: string;
  error?: string;
  parsedBody?: FormatErrorResponse;
}> {
  return new Promise((resolve) => {
    const url = new URL(REGISTER_PATH, BASE_URL);
    const bodyString = JSON.stringify(body);

    const options: http.RequestOptions = {
      hostname: url.hostname,
      port: url.port,
      path: url.pathname,
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Content-Length': Buffer.byteLength(bodyString),
        ...headers,
      },
    };

    const req = http.request(options, (res) => {
      let bodyStr = '';
      res.on('data', (chunk: Buffer) => (bodyStr += chunk.toString()));
      res.on('end', () => {
        let parsedBody: FormatErrorResponse | undefined;
        try {
          parsedBody = JSON.parse(bodyStr) as FormatErrorResponse;
        } catch {
          // Body is not JSON - that's fine, we'll still check status code
        }

        resolve({
          statusCode: res.statusCode || 0,
          headers: res.headers,
          body: bodyStr,
          parsedBody,
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

    req.write(bodyString);
    req.end();
  });
}

// ============================================================================
// CLAIM ASPECT 1: Email validation
// ============================================================================

/**
 * Test 1.1: Valid email format is accepted
 *
 * Falsification: If the endpoint incorrectly rejects a valid email,
 * it would return 400 instead of 201/200.
 *
 * Oracle: HTTP 201 or 200 on valid email "user@example.com".
 *
 * This test would fail if valid emails are rejected because the response
 * would be 400 instead of success status.
 *
 * Coverage trace: Forces the email format validation path in user-schema.ts.
 * A valid email must pass through without triggering the 400 rejection path.
 */
async function testValidEmailAccepted(): Promise<void> {
  console.log('TEST 1.1: Valid email is accepted');

  const validEmail = 'user@example.com';
  const response = await makeRegisterRequest({
    email: validEmail,
    password: 'ValidPass1',
    username: 'validuser',
    age: 25,
  });

  console.log(`  Status: ${response.statusCode}`);
  console.log(`  Expected: 200 or 201`);

  if (response.statusCode !== 200 && response.statusCode !== 201) {
    throw new Error(
      `Expected HTTP 200/201 for valid email "${validEmail}", ` +
      `got ${response.statusCode} instead. ` +
      `Valid emails must NOT be rejected!`
    );
  }
  console.log('  PASS: Valid email accepted');
}

/**
 * Test 1.2: Invalid email "notanemail" is rejected with 400
 *
 * Falsification: If the endpoint accepts "notanemail" as valid,
 * it would return 200/201 instead of 400.
 *
 * Oracle: HTTP 400 with formatError() structure showing email validation error.
 *
 * This test would fail if "notanemail" is accepted because the response
 * would be 200/201 instead of 400.
 *
 * Coverage trace: Forces the email format validation path where regex/format
 * checking occurs. The validation must reject strings without "@" and domain.
 */
async function testInvalidEmail_NoAtSymbol(): Promise<void> {
  console.log('TEST 1.2: Invalid email "notanemail" is rejected');

  const response = await makeRegisterRequest({
    email: 'notanemail',
    password: 'ValidPass1',
    username: 'validuser',
    age: 25,
  });

  console.log(`  Status: ${response.statusCode}`);
  console.log(`  Expected: 400`);

  if (response.statusCode !== 400) {
    throw new Error(
      `Expected HTTP 400 for invalid email "notanemail", ` +
      `got ${response.statusCode} instead. ` +
      `Invalid emails must be rejected!`
    );
  }

  // Verify formatError() structure
  if (!response.parsedBody) {
    throw new Error(
      `Expected formatError() response body (JSON), but body was: "${response.body}". ` +
      `The response must use formatError(code, message, details?) structure.`
    );
  }

  if (response.parsedBody.code !== 400) {
    throw new Error(
      `Expected formatError().code to be 400, got ${response.parsedBody.code}`
    );
  }

  if (!response.parsedBody.details?.email) {
    throw new Error(
      `Expected formatError().details.email to contain validation error, ` +
      `but details were: ${JSON.stringify(response.parsedBody.details)}. ` +
      `Field-level errors must be included in details!`
    );
  }

  console.log('  PASS: Invalid email "notanemail" rejected with formatError() structure');
}

/**
 * Test 1.3: Invalid email "missing@" is rejected with 400
 *
 * Falsification: If the endpoint accepts "missing@" as valid,
 * it would return 200/201 instead of 400.
 *
 * Oracle: HTTP 400 with formatError() structure showing email validation error.
 *
 * Coverage trace: Forces the email format validation path. Email with missing
 * domain must be rejected.
 */
async function testInvalidEmail_MissingDomain(): Promise<void> {
  console.log('TEST 1.3: Invalid email "missing@" is rejected');

  const response = await makeRegisterRequest({
    email: 'missing@',
    password: 'ValidPass1',
    username: 'validuser',
    age: 25,
  });

  console.log(`  Status: ${response.statusCode}`);
  console.log(`  Expected: 400`);

  if (response.statusCode !== 400) {
    throw new Error(
      `Expected HTTP 400 for invalid email "missing@", ` +
      `got ${response.statusCode} instead. ` +
      `Invalid emails must be rejected!`
    );
  }

  if (!response.parsedBody?.details?.email) {
    throw new Error(
      `Expected formatError().details.email validation error, ` +
      `but details were: ${JSON.stringify(response.parsedBody?.details)}`
    );
  }

  console.log('  PASS: Invalid email "missing@" rejected with formatError()');
}

/**
 * Test 1.4: Empty email is rejected with 400
 *
 * Falsification: If the endpoint accepts empty email as valid,
 * it would return 200/201 instead of 400.
 *
 * Oracle: HTTP 400 with formatError() structure showing email validation error.
 *
 * Coverage trace: Forces the email presence/format validation path.
 */
async function testInvalidEmail_Empty(): Promise<void> {
  console.log('TEST 1.4: Empty email is rejected');

  const response = await makeRegisterRequest({
    email: '',
    password: 'ValidPass1',
    username: 'validuser',
    age: 25,
  });

  console.log(`  Status: ${response.statusCode}`);
  console.log(`  Expected: 400`);

  if (response.statusCode !== 400) {
    throw new Error(
      `Expected HTTP 400 for empty email, ` +
      `got ${response.statusCode} instead. ` +
      `Empty emails must be rejected!`
    );
  }

  console.log('  PASS: Empty email rejected with 400');
}

// ============================================================================
// CLAIM ASPECT 2: Password validation
// ============================================================================

/**
 * Test 2.1: Valid password is accepted
 * Requirements: minimum 8 characters, at least one uppercase, one lowercase, one number
 *
 * Falsification: If the endpoint rejects a valid password,
 * it would return 400 instead of 201/200.
 *
 * Oracle: HTTP 201 or 200 on valid password "ValidPass1".
 *
 * This test would fail if valid passwords are rejected.
 *
 * Coverage trace: Forces the password validation path. A valid password
 * must pass all checks (length >= 8, has uppercase, has lowercase, has number).
 */
async function testValidPasswordAccepted(): Promise<void> {
  console.log('TEST 2.1: Valid password is accepted');

  const response = await makeRegisterRequest({
    email: 'user@example.com',
    password: 'ValidPass1',
    username: 'validuser',
    age: 25,
  });

  console.log(`  Status: ${response.statusCode}`);
  console.log(`  Expected: 200 or 201`);

  if (response.statusCode !== 200 && response.statusCode !== 201) {
    throw new Error(
      `Expected HTTP 200/201 for valid password "ValidPass1", ` +
      `got ${response.statusCode} instead. ` +
      `Valid passwords must NOT be rejected!`
    );
  }
  console.log('  PASS: Valid password accepted');
}

/**
 * Test 2.2: Password "short" (too short) is rejected with 400
 *
 * Falsification: If the endpoint accepts "short" as valid password,
 * it would return 200/201 instead of 400.
 *
 * Oracle: HTTP 400 with formatError() structure showing password validation error.
 *
 * This test would fail if "short" is accepted because the response would be
 * 200/201 instead of 400. The endpoint must enforce minimum 8 character length.
 *
 * Coverage trace: Forces the password length validation check (min 8 characters).
 */
async function testInvalidPassword_TooShort(): Promise<void> {
  console.log('TEST 2.2: Password "short" (too short) is rejected');

  const response = await makeRegisterRequest({
    email: 'user@example.com',
    password: 'short',
    username: 'validuser',
    age: 25,
  });

  console.log(`  Status: ${response.statusCode}`);
  console.log(`  Expected: 400`);

  if (response.statusCode !== 400) {
    throw new Error(
      `Expected HTTP 400 for password "short" (only 5 chars, need min 8), ` +
      `got ${response.statusCode} instead. ` +
      `Short passwords must be rejected!`
    );
  }

  if (!response.parsedBody?.details?.password) {
    throw new Error(
      `Expected formatError().details.password validation error, ` +
      `but details were: ${JSON.stringify(response.parsedBody?.details)}`
    );
  }

  console.log('  PASS: Short password rejected with formatError()');
}

/**
 * Test 2.3: Password "nouppercase1" (missing uppercase) is rejected with 400
 *
 * Falsification: If the endpoint accepts "nouppercase1" as valid,
 * it would return 200/201 instead of 400.
 *
 * Oracle: HTTP 400 with formatError() structure showing password validation error.
 *
 * This test would fail if passwords without uppercase are accepted.
 *
 * Coverage trace: Forces the password uppercase character check.
 */
async function testInvalidPassword_NoUppercase(): Promise<void> {
  console.log('TEST 2.3: Password "nouppercase1" (missing uppercase) is rejected');

  const response = await makeRegisterRequest({
    email: 'user@example.com',
    password: 'nouppercase1',
    username: 'validuser',
    age: 25,
  });

  console.log(`  Status: ${response.statusCode}`);
  console.log(`  Expected: 400`);

  if (response.statusCode !== 400) {
    throw new Error(
      `Expected HTTP 400 for password "nouppercase1" (no uppercase letter), ` +
      `got ${response.statusCode} instead. ` +
      `Passwords without uppercase must be rejected!`
    );
  }

  if (!response.parsedBody?.details?.password) {
    throw new Error(
      `Expected formatError().details.password validation error, ` +
      `but details were: ${JSON.stringify(response.parsedBody?.details)}`
    );
  }

  console.log('  PASS: Password without uppercase rejected with formatError()');
}

/**
 * Test 2.4: Password "NoLowerCase1" (missing lowercase) is rejected with 400
 *
 * Falsification: If the endpoint accepts "NoLowerCase1" as valid,
 * it would return 200/201 instead of 400.
 *
 * Oracle: HTTP 400 with formatError() structure showing password validation error.
 *
 * This test would fail if passwords without lowercase are accepted.
 *
 * Coverage trace: Forces the password lowercase character check.
 */
async function testInvalidPassword_NoLowercase(): Promise<void> {
  console.log('TEST 2.4: Password "NoLowerCase1" (missing lowercase) is rejected');

  const response = await makeRegisterRequest({
    email: 'user@example.com',
    password: 'NoLowerCase1',
    username: 'validuser',
    age: 25,
  });

  console.log(`  Status: ${response.statusCode}`);
  console.log(`  Expected: 400`);

  if (response.statusCode !== 400) {
    throw new Error(
      `Expected HTTP 400 for password "NoLowerCase1" (no lowercase letter), ` +
      `got ${response.statusCode} instead. ` +
      `Passwords without lowercase must be rejected!`
    );
  }

  if (!response.parsedBody?.details?.password) {
    throw new Error(
      `Expected formatError().details.password validation error, ` +
      `but details were: ${JSON.stringify(response.parsedBody?.details)}`
    );
  }

  console.log('  PASS: Password without lowercase rejected with formatError()');
}

/**
 * Test 2.5: Password "noNumberHere" (missing number) is rejected with 400
 *
 * Falsification: If the endpoint accepts "noNumberHere" as valid,
 * it would return 200/201 instead of 400.
 *
 * Oracle: HTTP 400 with formatError() structure showing password validation error.
 *
 * This test would fail if passwords without numbers are accepted.
 *
 * Coverage trace: Forces the password number check.
 */
async function testInvalidPassword_NoNumber(): Promise<void> {
  console.log('TEST 2.5: Password "noNumberHere" (missing number) is rejected');

  const response = await makeRegisterRequest({
    email: 'user@example.com',
    password: 'noNumberHere',
    username: 'validuser',
    age: 25,
  });

  console.log(`  Status: ${response.statusCode}`);
  console.log(`  Expected: 400`);

  if (response.statusCode !== 400) {
    throw new Error(
      `Expected HTTP 400 for password "noNumberHere" (no number), ` +
      `got ${response.statusCode} instead. ` +
      `Passwords without numbers must be rejected!`
    );
  }

  if (!response.parsedBody?.details?.password) {
    throw new Error(
      `Expected formatError().details.password validation error, ` +
      `but details were: ${JSON.stringify(response.parsedBody?.details)}`
    );
  }

  console.log('  PASS: Password without number rejected with formatError()');
}

// ============================================================================
// CLAIM ASPECT 3: Username validation
// ============================================================================

/**
 * Test 3.1: Valid username is accepted
 * Requirements: 3-30 characters, alphanumeric only
 *
 * Falsification: If the endpoint rejects a valid username,
 * it would return 400 instead of 201/200.
 *
 * Oracle: HTTP 201 or 200 on valid username "validuser".
 *
 * This test would fail if valid usernames are rejected.
 *
 * Coverage trace: Forces the username validation path. A valid username must
 * pass length (3-30) and character (alphanumeric only) checks.
 */
async function testValidUsernameAccepted(): Promise<void> {
  console.log('TEST 3.1: Valid username is accepted');

  const response = await makeRegisterRequest({
    email: 'user@example.com',
    password: 'ValidPass1',
    username: 'validuser',
    age: 25,
  });

  console.log(`  Status: ${response.statusCode}`);
  console.log(`  Expected: 200 or 201`);

  if (response.statusCode !== 200 && response.statusCode !== 201) {
    throw new Error(
      `Expected HTTP 200/201 for valid username "validuser", ` +
      `got ${response.statusCode} instead. ` +
      `Valid usernames must NOT be rejected!`
    );
  }
  console.log('  PASS: Valid username accepted');
}

/**
 * Test 3.2: Username "ab" (too short) is rejected with 400
 *
 * Falsification: If the endpoint accepts "ab" as valid username,
 * it would return 200/201 instead of 400.
 *
 * Oracle: HTTP 400 with formatError() structure showing username validation error.
 *
 * This test would fail if "ab" (2 chars, below minimum 3) is accepted.
 *
 * Coverage trace: Forces the username minimum length check (min 3 characters).
 */
async function testInvalidUsername_TooShort(): Promise<void> {
  console.log('TEST 3.2: Username "ab" (too short) is rejected');

  const response = await makeRegisterRequest({
    email: 'user@example.com',
    password: 'ValidPass1',
    username: 'ab',
    age: 25,
  });

  console.log(`  Status: ${response.statusCode}`);
  console.log(`  Expected: 400`);

  if (response.statusCode !== 400) {
    throw new Error(
      `Expected HTTP 400 for username "ab" (only 2 chars, need min 3), ` +
      `got ${response.statusCode} instead. ` +
      `Too-short usernames must be rejected!`
    );
  }

  if (!response.parsedBody?.details?.username) {
    throw new Error(
      `Expected formatError().details.username validation error, ` +
      `but details were: ${JSON.stringify(response.parsedBody?.details)}`
    );
  }

  console.log('  PASS: Username "ab" rejected with formatError()');
}

/**
 * Test 3.3: Username "thisusernameiswaytoolongforthissystem" (too long) is rejected
 *
 * Falsification: If the endpoint accepts an overlength username,
 * it would return 200/201 instead of 400.
 *
 * Oracle: HTTP 400 with formatError() structure showing username validation error.
 *
 * This test would fail if usernames over 30 characters are accepted.
 *
 * Coverage trace: Forces the username maximum length check (max 30 characters).
 */
async function testInvalidUsername_TooLong(): Promise<void> {
  console.log('TEST 3.3: Overlength username is rejected');

  const overlengthUsername = 'thisusernameiswaytoolongforthissystem'; // 38 chars

  const response = await makeRegisterRequest({
    email: 'user@example.com',
    password: 'ValidPass1',
    username: overlengthUsername,
    age: 25,
  });

  console.log(`  Status: ${response.statusCode}`);
  console.log(`  Expected: 400`);

  if (response.statusCode !== 400) {
    throw new Error(
      `Expected HTTP 400 for username "${overlengthUsername}" (${overlengthUsername.length} chars, max 30), ` +
      `got ${response.statusCode} instead. ` +
      `Overlength usernames must be rejected!`
    );
  }

  if (!response.parsedBody?.details?.username) {
    throw new Error(
      `Expected formatError().details.username validation error, ` +
      `but details were: ${JSON.stringify(response.parsedBody?.details)}`
    );
  }

  console.log('  PASS: Overlength username rejected with formatError()');
}

/**
 * Test 3.4: Username "user@name" (non-alphanumeric) is rejected
 *
 * Falsification: If the endpoint accepts "user@name" as valid,
 * it would return 200/201 instead of 400.
 *
 * Oracle: HTTP 400 with formatError() structure showing username validation error.
 *
 * This test would fail if usernames with special characters are accepted.
 *
 * Coverage trace: Forces the username character validation (alphanumeric only).
 */
async function testInvalidUsername_NonAlphanumeric(): Promise<void> {
  console.log('TEST 3.4: Username "user@name" (non-alphanumeric) is rejected');

  const response = await makeRegisterRequest({
    email: 'user@example.com',
    password: 'ValidPass1',
    username: 'user@name',
    age: 25,
  });

  console.log(`  Status: ${response.statusCode}`);
  console.log(`  Expected: 400`);

  if (response.statusCode !== 400) {
    throw new Error(
      `Expected HTTP 400 for username "user@name" (contains @, not alphanumeric), ` +
      `got ${response.statusCode} instead. ` +
      `Non-alphanumeric usernames must be rejected!`
    );
  }

  if (!response.parsedBody?.details?.username) {
    throw new Error(
      `Expected formatError().details.username validation error, ` +
      `but details were: ${JSON.stringify(response.parsedBody?.details)}`
    );
  }

  console.log('  PASS: Username "user@name" rejected with formatError()');
}

/**
 * Test 3.5: Username "user name" (contains space) is rejected
 *
 * Falsification: If the endpoint accepts "user name" as valid,
 * it would return 200/201 instead of 400.
 *
 * Oracle: HTTP 400 with formatError() structure showing username validation error.
 *
 * This test would fail if usernames with spaces are accepted.
 *
 * Coverage trace: Forces the username character validation (spaces are not alphanumeric).
 */
async function testInvalidUsername_ContainsSpace(): Promise<void> {
  console.log('TEST 3.5: Username "user name" (contains space) is rejected');

  const response = await makeRegisterRequest({
    email: 'user@example.com',
    password: 'ValidPass1',
    username: 'user name',
    age: 25,
  });

  console.log(`  Status: ${response.statusCode}`);
  console.log(`  Expected: 400`);

  if (response.statusCode !== 400) {
    throw new Error(
      `Expected HTTP 400 for username "user name" (contains space, not alphanumeric), ` +
      `got ${response.statusCode} instead. ` +
      `Usernames with spaces must be rejected!`
    );
  }

  if (!response.parsedBody?.details?.username) {
    throw new Error(
      `Expected formatError().details.username validation error, ` +
      `but details were: ${JSON.stringify(response.parsedBody?.details)}`
    );
  }

  console.log('  PASS: Username "user name" rejected with formatError()');
}

// ============================================================================
// CLAIM ASPECT 4: Age validation
// ============================================================================

/**
 * Test 4.1: Age omitted (optional field) is accepted
 *
 * Falsification: If the endpoint rejects registration when age is omitted,
 * it would return 400 instead of 201/200.
 *
 * Oracle: HTTP 201 or 200 when age field is not provided.
 *
 * This test would fail if age is required when it should be optional.
 *
 * Coverage trace: Forces the age field handling path. If age is optional,
 * omitting it must not trigger validation error.
 */
async function testValidAge_Omitted(): Promise<void> {
  console.log('TEST 4.1: Age omitted (optional) is accepted');

  const response = await makeRegisterRequest({
    email: 'user@example.com',
    password: 'ValidPass1',
    username: 'validuser',
    // age is intentionally omitted
  });

  console.log(`  Status: ${response.statusCode}`);
  console.log(`  Expected: 200 or 201`);

  if (response.statusCode !== 200 && response.statusCode !== 201) {
    throw new Error(
      `Expected HTTP 200/201 when age is omitted, ` +
      `got ${response.statusCode} instead. ` +
      `Age is optional and must NOT be required!`
    );
  }
  console.log('  PASS: Age omitted accepted');
}

/**
 * Test 4.2: Age 25 (valid) is accepted
 *
 * Falsification: If the endpoint rejects a valid age (>= 13),
 * it would return 400 instead of 201/200.
 *
 * Oracle: HTTP 201 or 200 on valid age 25.
 *
 * This test would fail if valid ages are rejected.
 *
 * Coverage trace: Forces the age validation path. Age >= 13 must pass.
 */
async function testValidAge_ValidNumber(): Promise<void> {
  console.log('TEST 4.2: Age 25 (valid) is accepted');

  const response = await makeRegisterRequest({
    email: 'user@example.com',
    password: 'ValidPass1',
    username: 'validuser',
    age: 25,
  });

  console.log(`  Status: ${response.statusCode}`);
  console.log(`  Expected: 200 or 201`);

  if (response.statusCode !== 200 && response.statusCode !== 201) {
    throw new Error(
      `Expected HTTP 200/201 for valid age 25, ` +
      `got ${response.statusCode} instead. ` +
      `Valid ages must NOT be rejected!`
    );
  }
  console.log('  PASS: Age 25 accepted');
}

/**
 * Test 4.3: Age 12 (below minimum) is rejected with 400
 *
 * Falsification: If the endpoint accepts age 12,
 * it would return 200/201 instead of 400.
 *
 * Oracle: HTTP 400 with formatError() structure showing age validation error.
 *
 * This test would fail if age 12 is accepted (minimum is 13).
 *
 * Coverage trace: Forces the age minimum check (must be >= 13).
 */
async function testInvalidAge_TooYoung(): Promise<void> {
  console.log('TEST 4.3: Age 12 (below minimum 13) is rejected');

  const response = await makeRegisterRequest({
    email: 'user@example.com',
    password: 'ValidPass1',
    username: 'validuser',
    age: 12,
  });

  console.log(`  Status: ${response.statusCode}`);
  console.log(`  Expected: 400`);

  if (response.statusCode !== 400) {
    throw new Error(
      `Expected HTTP 400 for age 12 (below minimum 13), ` +
      `got ${response.statusCode} instead. ` +
      `Ages below 13 must be rejected!`
    );
  }

  if (!response.parsedBody?.details?.age) {
    throw new Error(
      `Expected formatError().details.age validation error, ` +
      `but details were: ${JSON.stringify(response.parsedBody?.details)}`
    );
  }

  console.log('  PASS: Age 12 rejected with formatError()');
}

/**
 * Test 4.4: Age 8 (clearly too young) is rejected with 400
 *
 * Falsification: If the endpoint accepts age 8,
 * it would return 200/201 instead of 400.
 *
 * Oracle: HTTP 400 with formatError() structure showing age validation error.
 *
 * This test would fail if age 8 is accepted.
 *
 * Coverage trace: Forces the age minimum check with a clearly invalid value.
 */
async function testInvalidAge_ClearlyTooYoung(): Promise<void> {
  console.log('TEST 4.4: Age 8 (clearly too young) is rejected');

  const response = await makeRegisterRequest({
    email: 'user@example.com',
    password: 'ValidPass1',
    username: 'validuser',
    age: 8,
  });

  console.log(`  Status: ${response.statusCode}`);
  console.log(`  Expected: 400`);

  if (response.statusCode !== 400) {
    throw new Error(
      `Expected HTTP 400 for age 8 (below minimum 13), ` +
      `got ${response.statusCode} instead. ` +
      `Ages below 13 must be rejected!`
    );
  }

  if (!response.parsedBody?.details?.age) {
    throw new Error(
      `Expected formatError().details.age validation error, ` +
      `but details were: ${JSON.stringify(response.parsedBody?.details)}`
    );
  }

  console.log('  PASS: Age 8 rejected with formatError()');
}

// ============================================================================
// CLAIM ASPECT 5: Multiple validation errors returned together
// ============================================================================

/**
 * Test 5.1: Multiple invalid fields return all validation errors
 *
 * Falsification: If the endpoint returns only the first error it finds,
 * it would not include all validation errors in details.
 *
 * Oracle: HTTP 400 with formatError() structure where details contains
 * errors for ALL invalid fields (email AND password AND username).
 *
 * This test would fail if only one error is returned instead of all.
 *
 * Coverage trace: Forces the multi-field validation path where all fields
 * are validated before responding, collecting all errors together.
 */
async function testMultipleValidationErrors(): Promise<void> {
  console.log('TEST 5.1: Multiple invalid fields return all validation errors');

  const response = await makeRegisterRequest({
    email: 'notanemail',       // Invalid
    password: 'short',         // Invalid
    username: 'ab',            // Invalid
    age: 12,                   // Invalid
  });

  console.log(`  Status: ${response.statusCode}`);
  console.log(`  Expected: 400`);

  if (response.statusCode !== 400) {
    throw new Error(
      `Expected HTTP 400 for multiple invalid fields, ` +
      `got ${response.statusCode} instead. ` +
      `Requests with multiple errors must still return 400!`
    );
  }

  // Check that formatError() structure is used
  if (!response.parsedBody) {
    throw new Error(
      `Expected formatError() response body, but body was: "${response.body}"`
    );
  }

  // Check that details contains errors for ALL invalid fields
  const details = response.parsedBody.details || {};
  const invalidFields = ['email', 'password', 'username', 'age'];
  const missingErrors: string[] = [];

  for (const field of invalidFields) {
    if (!details[field]) {
      missingErrors.push(field);
    }
  }

  if (missingErrors.length > 0) {
    throw new Error(
      `Expected formatError().details to contain errors for all invalid fields, ` +
      `but missing errors for: ${missingErrors.join(', ')}. ` +
      `Details were: ${JSON.stringify(details)}. ` +
      `All field-level validation errors must be returned together!`
    );
  }

  console.log('  PASS: All 4 invalid fields returned in formatError().details');
}

// ============================================================================
// CLAIM ASPECT 6: formatError() response structure verification
// ============================================================================

/**
 * Test 6.1: 400 response uses formatError() structure exactly
 *
 * Falsification: If the endpoint returns a non-formatError() error structure,
 * it would not match the expected { code, message, details } pattern.
 *
 * Oracle: Response body is valid JSON with exactly:
 *   { code: 400, message: string, details?: {...} }
 *
 * This test would fail if the error response structure doesn't match formatError().
 *
 * Coverage trace: Forces the error response construction path to verify it uses
 * formatError() correctly.
 */
async function testFormatErrorStructure(): Promise<void> {
  console.log('TEST 6.1: 400 response uses formatError() structure exactly');

  const response = await makeRegisterRequest({
    email: 'bademail',
    password: 'badpass',
    username: 'bad',
    age: 5,
  });

  console.log(`  Status: ${response.statusCode}`);
  console.log(`  Expected: 400`);

  if (response.statusCode !== 400) {
    throw new Error(
      `Expected HTTP 400, got ${response.statusCode}`
    );
  }

  if (!response.parsedBody) {
    throw new Error(
      `Expected response body to be valid JSON, but was: "${response.body}". ` +
      `formatError() must return JSON.`
    );
  }

  const { code, message, details } = response.parsedBody;

  // Verify 'code' is exactly 400
  if (code !== 400) {
    throw new Error(
      `Expected formatError().code to be 400, got ${code}. ` +
      `The error code must match the HTTP status.`
    );
  }

  // Verify 'message' is a non-empty string
  if (typeof message !== 'string' || message.trim().length === 0) {
    throw new Error(
      `Expected formatError().message to be a non-empty string, got: ${JSON.stringify(message)}. ` +
      `A human-readable error message is required.`
    );
  }

  // Verify 'details' is an object (if present)
  if (details !== undefined && (typeof details !== 'object' || details === null || Array.isArray(details))) {
    throw new Error(
      `Expected formatError().details to be an object or undefined, got: ${JSON.stringify(details)}. ` +
      `Field-level errors must be in a plain object.`
    );
  }

  // Verify details contains field-level errors
  if (!details || Object.keys(details).length === 0) {
    throw new Error(
      `Expected formatError().details to contain field-level validation errors, ` +
      `but it was empty or undefined. ` +
      `All invalid fields must be listed in details.`
    );
  }

  console.log('  PASS: Response uses formatError() structure exactly');
  console.log(`    code: ${code}`);
  console.log(`    message: "${message}"`);
  console.log(`    details: ${JSON.stringify(details)}`);
}

// ============================================================================
// Test runner
// ============================================================================

async function runTests(): Promise<void> {
  console.log('='.repeat(70));
  console.log('RED-PHASE TESTS: /api/register input validation');
  console.log('='.repeat(70));
  console.log('');
  console.log('Claim: "When the registration endpoint receives invalid input,');
  console.log('it must return HTTP 400 using formatError() with field details."');
  console.log('');
  console.log('Coverage target:');
  console.log('  - email: valid + 3 invalid (no @, no domain, empty)');
  console.log('  - password: valid + 4 invalid (short, no upper, no lower, no num)');
  console.log('  - username: valid + 4 invalid (too short, too long, @, space)');
  console.log('  - age: valid (omitted, valid) + 2 invalid (< 13)');
  console.log('  - Multiple errors returned together');
  console.log('  - formatError() response structure');
  console.log('');

  const tests: Array<{ name: string; fn: () => Promise<void> }> = [
    // Email validation (4 tests)
    { name: '1.1: Valid email is accepted', fn: testValidEmailAccepted },
    { name: '1.2: Invalid email "notanemail" is rejected', fn: testInvalidEmail_NoAtSymbol },
    { name: '1.3: Invalid email "missing@" is rejected', fn: testInvalidEmail_MissingDomain },
    { name: '1.4: Empty email is rejected', fn: testInvalidEmail_Empty },
    // Password validation (5 tests)
    { name: '2.1: Valid password is accepted', fn: testValidPasswordAccepted },
    { name: '2.2: Password "short" is rejected', fn: testInvalidPassword_TooShort },
    { name: '2.3: Password "nouppercase1" is rejected', fn: testInvalidPassword_NoUppercase },
    { name: '2.4: Password "NoLowerCase1" is rejected', fn: testInvalidPassword_NoLowercase },
    { name: '2.5: Password "noNumberHere" is rejected', fn: testInvalidPassword_NoNumber },
    // Username validation (5 tests)
    { name: '3.1: Valid username is accepted', fn: testValidUsernameAccepted },
    { name: '3.2: Username "ab" is rejected', fn: testInvalidUsername_TooShort },
    { name: '3.3: Overlength username is rejected', fn: testInvalidUsername_TooLong },
    { name: '3.4: Username "user@name" is rejected', fn: testInvalidUsername_NonAlphanumeric },
    { name: '3.5: Username "user name" is rejected', fn: testInvalidUsername_ContainsSpace },
    // Age validation (4 tests)
    { name: '4.1: Age omitted (optional) is accepted', fn: testValidAge_Omitted },
    { name: '4.2: Age 25 (valid) is accepted', fn: testValidAge_ValidNumber },
    { name: '4.3: Age 12 is rejected', fn: testInvalidAge_TooYoung },
    { name: '4.4: Age 8 is rejected', fn: testInvalidAge_ClearlyTooYoung },
    // Multi-field and structure (2 tests)
    { name: '5.1: Multiple errors returned together', fn: testMultipleValidationErrors },
    { name: '6.1: formatError() structure verified', fn: testFormatErrorStructure },
  ];

  let passed = 0;
  let failed = 0;
  const failures: Array<{ test: string; error: string }> = [];

  for (let i = 0; i < tests.length; i++) {
    const { name, fn } = tests[i];
    const testIndex = i + 1;
    console.log('');
    console.log(`[${testIndex}/${tests.length}] ${name}`);
    console.log('-'.repeat(50));

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
    console.log('  1. /api/register endpoint does not exist');
    console.log('  2. formatError() from src/api/errors/format.ts does not exist');
    console.log('  3. src/validation/user-schema.ts does not exist');
    console.log('  4. Server may not be running (ECONNREFUSED)');
    console.log('');
    console.log('These tests will PASS once the registration endpoint:');
    console.log('  - Validates email, password, username, age fields');
    console.log('  - Returns HTTP 400 for invalid input');
    console.log('  - Uses formatError(code, message, details) structure');
    console.log('  - Returns field-level errors in details');
    process.exit(1);
  } else {
    console.log('All tests passed! Input validation is working correctly.');
    process.exit(0);
  }
}

// Export for potential use by other test runners
export { runTests, makeRegisterRequest };

// Run tests when this file is executed directly
runTests().catch((err) => {
  console.error('Test runner error:', err);
  process.exit(1);
});
