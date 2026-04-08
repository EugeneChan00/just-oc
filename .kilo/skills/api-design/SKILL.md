---
name: api-design
description: Use when designing REST APIs, creating API endpoints, or discussing API architecture
---

# API Design Guidelines

When designing REST APIs, follow these conventions:

## URL Structure

- Use plural nouns for resources: `/users`, `/orders`
- Use kebab-case for multi-word resources: `/order-items`
- Nest related resources: `/users/{id}/orders`
- Use query parameters for filtering, sorting, pagination

## HTTP Methods

| Method | Usage |
|--------|-------|
| GET | Retrieve resources (idempotent) |
| POST | Create new resources |
| PUT | Replace entire resource (idempotent) |
| PATCH | Partial update |
| DELETE | Remove resource (idempotent) |

## Response Codes

| Code | Meaning |
|------|---------|
| 200 | Success |
| 201 | Created |
| 400 | Bad Request |
| 401 | Unauthorized |
| 403 | Forbidden |
| 404 | Not Found |
| 500 | Server Error |

## Best Practices

1. **Versioning**: `/v1/users`, `/v2/users`
2. **Consistency**: Same pattern across all endpoints
3. **Documentation**: OpenAPI/Swagger specs
4. **Error Handling**: Consistent error response format
5. **Pagination**: Use cursor-based for large datasets

## Example Error Response

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid input",
    "details": [
      {"field": "email", "message": "Invalid format"}
    ]
  }
}
```
