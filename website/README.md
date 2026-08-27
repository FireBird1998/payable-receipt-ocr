# payable-receipt-ocr-docs

Fumadocs static documentation site for `payable-receipt-ocr`.

## Commands

```bash
npm run dev
npm run build
npm run lint
npm run types:check
```

## Static export output

- `npm run build` runs the Next.js static export build.
- The generated static site is emitted to `website/out/`.

## GitHub Pages basePath behavior

- Production deploy target: `https://firebird1998.github.io/payable-receipt-ocr/`
- When `GITHUB_ACTIONS=true`, Next config applies:
  - `basePath: /payable-receipt-ocr`
  - matching `assetPrefix` for static assets
- Local development stays at root (`/`) with no basePath so docs and app routes behave normally on `http://localhost:3000`.

The `Documentation` GitHub Actions workflow verifies pull requests and deploys `website/out/` from
`main`. The repository's Pages source must be set to **GitHub Actions** before the first deployment;
the previous legacy `/docs` source can remain in place until then.
