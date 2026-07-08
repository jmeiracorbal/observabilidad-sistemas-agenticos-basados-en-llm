# Observability UI

Frontend React + Vite para explorar las ejecuciones del POC de observabilidad.

## Funcionalidades iniciales

- Lista de `runs` desde `observability-api`.
- Resumen de una ejecución.
- Timeline secuencial de spans, llamadas a modelo, tools, memoria y errores.
- Árbol jerárquico de spans.
- Diagrama de artefactos con React Flow.
- Inspector JSON para trabajar con los payloads reales.

## Configuración

No se usan archivos `.env`. En Docker Compose se definen variables de entorno:

- `OBSERVABILITY_API_URL`: URL pública que usará el navegador para llamar a `observability-api`.
- `APP_TITLE`: título mostrado en el dashboard.

En desarrollo con Vite también se aceptan variables `VITE_OBSERVABILITY_API_URL` y `VITE_APP_TITLE`.

## Comandos

```bash
npm install
npm run dev
npm run build
npm run typecheck
```
