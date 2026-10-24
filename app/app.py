"""Dashboard TFM · Agua y viñedo en La Rioja (Databricks App con Streamlit).

Lee solo tablas de gold, ops y ref a través del SQL warehouse, con el service
principal de la app (permisos de solo lectura concedidos en pipeline/05_governance).
"""
import os

import altair as alt
import pandas as pd
import streamlit as st
from databricks import sql
from databricks.sdk.core import Config

CATALOG = os.getenv("TFM_CATALOG", "tfm_embalses")
WAREHOUSE = os.getenv("DATABRICKS_WAREHOUSE_ID")

st.set_page_config(page_title="Agua y viñedo · La Rioja", page_icon="🍇", layout="wide")

COLOR_CALIF = {"Excelente": "#7b1e3a", "Muy buena": "#b5475f", "Buena": "#e3a5b3", "Sin calificar": "#b8b8b8"}


@st.cache_resource
def conexion():
    cfg = Config()
    return sql.connect(server_hostname=cfg.host,
                       http_path=f"/sql/1.0/warehouses/{WAREHOUSE}",
                       credentials_provider=lambda: cfg.authenticate)


@st.cache_data(ttl=600)
def leer(query: str) -> pd.DataFrame:
    with conexion().cursor() as cur:
        cur.execute(query.format(c=CATALOG))
        return cur.fetchall_arrow().to_pandas()


st.title("🍇 Agua y viñedo en La Rioja")
st.caption("Condiciones hídricas y climáticas de la campaña frente a las añadas DOCa · "
           "Fuentes: AEMET (estación 9170 Logroño), MITECO (embalses del Ebro), Consejo Regulador DOCa Rioja")

tab_negocio, tab_salud = st.tabs(["Campaña y reserva", "Salud del pipeline"])

# --------------------------------------------------------------------------
with tab_negocio:
    kpis = leer("SELECT kpi, valor, nota FROM {c}.gold.kpis").set_index("kpi")

    def kpi(nombre, campo, fmt, delta=None):
        v = kpis.loc[campo, "valor"] if campo in kpis.index else None
        d = kpis.loc[delta, "valor"] if delta and delta in kpis.index else None
        nombre.metric(label=kpis.loc[campo, "nota"] if campo in kpis.index else campo,
                      value=fmt.format(v) if v is not None and pd.notna(v) else "—",
                      delta=f"{d:+.1f} pts vs año anterior" if d is not None and pd.notna(d) else None)

    c1, c2, c3 = st.columns(3)
    c1.markdown("**Reserva cuenca del Ebro**")
    kpi(c1, "reserva_ebro_pct", "{:.1f} %", "variacion_anual_pts")
    c2.markdown("**Lluvia de la campaña**")
    kpi(c2, "lluvia_campana_mm", "{:.0f} mm")
    c3.markdown("**Grados-día de Winkler**")
    kpi(c3, "winkler_campana_gdd", "{:.0f} GDD")

    st.subheader("Cada campaña frente a su calificación DOCa")
    camp = leer("""SELECT anyo, lluvia_campana_mm, winkler_gdd, reserva_media_pct, completitud_pct,
                          region_winkler, coalesce(calificacion, 'Sin calificar') AS calificacion, campana_en_curso
                   FROM {c}.gold.campana_vitivinicola WHERE winkler_gdd IS NOT NULL ORDER BY anyo""")
    puntos = alt.Chart(camp).mark_circle(size=160, opacity=0.9).encode(
        x=alt.X("winkler_gdd:Q", title="Grados-día de Winkler (abr-oct)", scale=alt.Scale(zero=False)),
        y=alt.Y("lluvia_campana_mm:Q", title="Lluvia de la campaña (mm)"),
        color=alt.Color("calificacion:N", title="Calificación DOCa",
                        scale=alt.Scale(domain=list(COLOR_CALIF), range=list(COLOR_CALIF.values()))),
        tooltip=["anyo", "calificacion", "winkler_gdd", "lluvia_campana_mm", "reserva_media_pct", "completitud_pct"],
    )
    etiquetas = alt.Chart(camp).mark_text(dy=-12, fontSize=11).encode(
        x="winkler_gdd:Q", y="lluvia_campana_mm:Q", text="anyo:N")
    st.altair_chart((puntos + etiquetas).properties(height=420), use_container_width=True)
    st.caption("Lectura descriptiva, no predictiva: cada punto es una campaña. La de este año aparece "
               "'Sin calificar' hasta la calificación oficial de primavera.")

    st.subheader("Reserva de la cuenca del Ebro")
    reserva = leer("SELECT fecha, pct_capacidad FROM {c}.gold.reserva_ebro_semanal WHERE fecha >= date'2000-01-01' ORDER BY fecha")
    reserva["fecha"] = pd.to_datetime(reserva["fecha"])
    st.altair_chart(alt.Chart(reserva).mark_line(color="#2f6690").encode(
        x=alt.X("fecha:T", title=None), y=alt.Y("pct_capacidad:Q", title="% de capacidad"),
        tooltip=["fecha:T", "pct_capacidad"]).properties(height=280), use_container_width=True)

    with st.expander("Tabla de campañas"):
        st.dataframe(camp.sort_values("anyo", ascending=False), hide_index=True, use_container_width=True)

# --------------------------------------------------------------------------
with tab_salud:
    st.subheader("Ejecuciones del pipeline")
    runs = leer("""SELECT run_id, min(inicio) AS inicio,
                          max(CASE WHEN estado = 'ERROR' THEN 1 ELSE 0 END) AS con_error,
                          concat_ws(' · ', collect_list(concat(paso, ' ', fuente, ': ', estado))) AS pasos
                   FROM {c}.ops.run_log GROUP BY run_id ORDER BY inicio DESC LIMIT 30""")
    runs["resultado"] = runs["con_error"].map({0: "✅ OK", 1: "❌ Error"})
    st.dataframe(runs[["inicio", "resultado", "run_id", "pasos"]], hide_index=True, use_container_width=True)

    st.subheader("Controles de calidad · última ejecución")
    cal = leer("""SELECT control, tabla, nivel, ok, valor, umbral, detalle, ts FROM {c}.ops.quality_results
                  WHERE run_id = (SELECT run_id FROM {c}.ops.quality_results ORDER BY ts DESC LIMIT 1)
                  ORDER BY nivel, control""")
    if not cal.empty:
        a, b, c = st.columns(3)
        a.metric("Controles", len(cal))
        b.metric("Críticos fallidos", int(((cal.nivel == "critica") & ~cal.ok).sum()))
        c.metric("Avisos", int(((cal.nivel == "aviso") & ~cal.ok).sum()))
        cal["ok"] = cal["ok"].map({True: "✔", False: "✘"})
        st.dataframe(cal, hide_index=True, use_container_width=True)

    st.subheader("Evolución de los controles")
    hist = leer("""SELECT substr(ts, 1, 10) AS dia, nivel,
                          sum(CASE WHEN ok THEN 1 ELSE 0 END) AS superados,
                          sum(CASE WHEN ok THEN 0 ELSE 1 END) AS fallidos
                   FROM {c}.ops.quality_results GROUP BY 1, 2 ORDER BY 1""")
    if not hist.empty:
        st.altair_chart(alt.Chart(hist).mark_bar().encode(
            x=alt.X("dia:N", title=None), y=alt.Y("fallidos:Q", title="Controles fallidos"),
            color=alt.Color("nivel:N", scale=alt.Scale(domain=["critica", "aviso"], range=["#b3261e", "#e0a100"])),
            tooltip=["dia", "nivel", "superados", "fallidos"]).properties(height=220), use_container_width=True)
        st.caption("Barras vacías = todos los controles superados ese día.")

    st.subheader("Ficheros de MITECO cargados")
    st.dataframe(leer("SELECT ts, sha256, bytes, ruta_raw FROM {c}.ops.source_files ORDER BY ts DESC"),
                 hide_index=True, use_container_width=True)
