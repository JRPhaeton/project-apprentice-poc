import tseslint from 'typescript-eslint';

export default tseslint.config(
    {
        ignores: ['dist/**', 'node_modules/**', 'playwright-report/**', 'test-results/**']
    },
    ...tseslint.configs.recommended,
    {
        // §3 of docs/PLAN.md: explicit `any` is banned in the pure core.
        files: ['src/core/**/*.ts'],
        rules: {
            '@typescript-eslint/no-explicit-any': 'error'
        }
    }
);
