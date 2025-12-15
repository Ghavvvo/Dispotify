

This template provides a minimal setup to get React working in Vite with HMR and some ESLint rules.

Currently, two official plugins are available:

- [@vitejs/plugin-react](https:
- [@vitejs/plugin-react-swc](https:



The React Compiler is not enabled on this template because of its impact on dev & build performances. To add it, see [this documentation](https:



If you are developing a production application, we recommend updating the configuration to enable type-aware lint rules:

```js
export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['***.{ts,tsx}'],
    extends: [
      
      
      reactX.configs['recommended-typescript'],
      
      reactDom.configs.recommended,
    ],
    languageOptions: {
      parserOptions: {
        project: ['./tsconfig.node.json', './tsconfig.app.json'],
        tsconfigRootDir: import.meta.dirname,
      },
      
    },
  },
])
```
