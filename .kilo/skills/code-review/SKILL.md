---
name: code-review
description: Use when reviewing code changes, pull requests, or performing code quality assessments
---

# Code Review Guidelines

When reviewing code, focus on these key areas:

## Review Checklist

### Correctness
- Does the code do what it's supposed to do?
- Are edge cases handled?
- Are there potential bugs or race conditions?

### Security
- Input validation and sanitization
- Authentication and authorization
- No hardcoded secrets or credentials
- Parameterized queries for database access

### Performance
- Appropriate data structures and algorithms
- Database queries are optimized
- No unnecessary computations or allocations
- Caching where appropriate

### Maintainability
- Clear, descriptive names
- Code is self-documenting
- Appropriate comments for complex logic
- DRY - Don't Repeat Yourself

### Testing
- Adequate test coverage
- Tests cover edge cases
- Tests are isolated and deterministic

## Feedback Style

- Be constructive and specific
- Point to exact location (file:line)
- Suggest improvements, don't dictate
- Explain the "why" behind feedback

## Response Format

```markdown
## Summary
Brief overview of the changes

## Issues Found
1. **[Severity]**: Description
   - Location: file:line
   - Suggestion: How to fix

## Recommendations
- Additional improvements to consider

## Approved with Suggestions
OR

## Request Changes
```
