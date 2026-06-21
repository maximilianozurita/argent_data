---
name: snapshot-cambiario
description: >
  Usar cuando el usuario pide "el panorama del dólar", "cómo está el dólar hoy",
  un resumen cambiario, o la brecha entre el oficial y los paralelos. Arma una
  foto estándar de las cotizaciones del dólar en Argentina con la brecha calculada.
---

# Snapshot cambiario

Cuando se pida un panorama general del dólar (no una serie puntual), seguí este flujo:

1. Llamá a `list_series` y quedate con las series cambiarias relevantes:
   oficial, blue, MEP y CCL (filtrá por categoría "cambiario").
2. Para cada una, llamá a `get_latest_value`.
3. Calculá la **brecha** de cada paralelo contra el oficial, de forma explícita:
   `brecha % = (paralelo − oficial) / oficial × 100`
   Mostrá los dos valores y la fecha de cada uno; si las fechas difieren, aclaralo.
4. Presentá el resultado en esta tabla, siempre en este orden:

   | Serie    | Valor (ARS/USD) | Fecha       | Brecha vs oficial |
   |----------|-----------------|-------------|-------------------|
   | Oficial  | …               | YYYY-MM-DD  | —                 |
   | Blue     | …               | YYYY-MM-DD  | +XX,X %           |
   | MEP      | …               | YYYY-MM-DD  | +XX,X %           |
   | CCL      | …               | YYYY-MM-DD  | +XX,X %           |

Reglas (heredan del system prompt): solo datos que vengan de las tools, nunca
inventás números, no das recomendaciones de inversión. Si falta alguna serie en
el catálogo, omitila de la tabla y aclaralo en una línea.
