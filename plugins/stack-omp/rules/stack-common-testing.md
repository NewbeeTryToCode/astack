# Testing Requirements

In the `stack` plugin, pstack owns verification. These rules defer to its principles.

## What a test is for

- A test asserts what the code's users can observe, so it fails when that behavior breaks and keeps passing when only the internals change (principle `test-behavior-not-implementation`).
- Unit tests show branch behavior, not bug absence. A change is done when the real artifact was checked: the command run, the value read back, the flow driven (principle `prove-it-works`).
- Coverage is a signal, not a gate. Report it when it moved, and never add a test only to raise it.

## When to write the test first

Write the failing test first when a cheap local test path exists, and commit it before the fix (the `tdd` skill). Skip it when the test would be expensive, integration-heavy, or unclear, and prove the change on the real surface instead.

## Failing tests

1. Reproduce the failure and read its output before changing anything.
2. Check test isolation and mocks.
3. Fix the code, not the test, unless the test asserts something the users cannot observe.
4. Never skip, disable or loosen a test to get green.

## Test Structure (AAA Pattern)

Prefer Arrange-Act-Assert structure for tests:

```typescript
test('calculates similarity correctly', () => {
  // Arrange
  const vector1 = [1, 0, 0]
  const vector2 = [0, 1, 0]

  // Act
  const similarity = calculateCosineSimilarity(vector1, vector2)

  // Assert
  expect(similarity).toBe(0)
})
```

### Test Naming

Use descriptive names that explain the behavior under test:

```typescript
test('returns empty array when no markets match query', () => {})
test('throws error when API key is missing', () => {})
test('falls back to substring search when Redis is unavailable', () => {})
```
