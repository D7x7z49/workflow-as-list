<!-- test/README.md -->
# Common sense for test engineering

Write tests that verify necessary conditions only. No test suite covers infinite input space. Focus on high-importance inputs and consolidate logic you trust. Use monitoring and fast rollback for untested areas.

Before writing a test, decide its type by scope.

- Unit tests
  - File pattern: `*.unit.test.*`
  - One test per cyclomatic complexity branch
  - No external calls; use in-memory fakes

- Component tests
  - File pattern: `*.component.test.*`
  - Cover public interface main scenarios
  - Also cover critical exceptions

- Integration tests
  - File pattern: `*.integration.test.*`
  - Test only actually used component combinations
  - Mock only at component boundaries

- End-to-end tests
  - File pattern: `*.e2e.test.*`
  - Limit to five or fifteen workflows
  - Include only workflows with direct business impact

After writing a test, run it with your language's standard test runner. Filter by naming patterns via regex or name matching. No specific command is given; adapt to your toolchain.

For external dependencies, mock according to test type.

- Unit tests: no external calls
- Component tests: stub all external dependencies
- Integration tests: mock at boundaries, test real interactions once safe
- E2E tests: use real dependencies in a controlled environment

Do not treat coverage as a goal. Use coverage only to find uncovered high-importance inputs.

Before committing a test, ask yourself five questions.

- Without this test, does your confidence in key logic drop?
- On failure, must you fix immediately or can it wait?
- Three months later, will you understand why this test exists?
- Where would the system break if you delete this test?
- Are you testing logic or implementation details?

Add UNIX-style comments only for non-obvious assertions or data setup. Keep comments short. Use prepositions instead of colons or dashes. For example, write "# check for empty list" not "# verify empty list returns zero: edge case".

Remember the limitations of this approach. It is not suitable for safety-critical or life-critical systems. Rely on monitoring and fast rollback for untested areas.
