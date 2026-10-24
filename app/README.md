# Dashboard · Databricks App (Streamlit)

1. *Compute → Apps → Create app → Custom*. Nombre: `tfm-embalses-dashboard`.
2. En **Resources**, añade el **SQL warehouse** con permiso *Can use* y la clave `sql-warehouse` (la que usa `app.yaml`).
3. Crea la app y, en **Deploy**, indica la carpeta `app` de este repositorio (Git folder).
4. Copia el identificador del *service principal* de la app (pestaña **Authorization**) y ejecuta
   `pipeline/05_governance.py` con ese valor en el widget `principal_app`: concede `SELECT` solo en `gold`, `ops` y `ref`.
5. Abre la URL de la app.

Free Edition para las apps a las 24 h: si la ves parada, pulsa **Start**.
