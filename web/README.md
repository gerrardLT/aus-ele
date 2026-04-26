# web

Frontend for the `aus-ele` analysis workspace.

## Stack

- React
- Vite
- Tailwind CSS
- Recharts
- Framer Motion

## Run

```bash
npm install
npm run dev
```

Default local URL:

```text
http://127.0.0.1:5173
```

## API Configuration

By default the app calls:

```text
http://127.0.0.1:8085/api
```

Override with:

```bash
set VITE_API_BASE=http://127.0.0.1:8085/api
```

## Checks

```bash
npm run lint
npm run build
```
