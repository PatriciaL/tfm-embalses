# Dashboard · Databricks App (Streamlit)

1. *Compute → Apps → Create app → Custom*. Nombre: `tfm-embalses-dashboard`.
2. En **Resources**, añade el **SQL warehouse** con permiso *Can use* y la clave `sql-warehouse` (la que usa `app.yaml`).
3. Crea la app y, en **Deploy**, indica la carpeta `app` de este repositorio (Git folder).
4. Concede a la app `USE CATALOG` en `tfm_embalses` y `USE SCHEMA` + `SELECT` solo en `gold`, `ops` y `ref`
   (Catalog Explorer › Permissions › Grant, buscando la app por su nombre). Verifica con `SHOW GRANTS`.
5. Abre la URL de la app.

Free Edition para las apps a las 24 h: si la ves parada, pulsa **Start**.
