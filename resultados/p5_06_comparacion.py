"""Compara una detección local con P5-05 sin presumir identidad entre plataformas."""

from __future__ import annotations


def _comparar_orden(detecciones: list[dict], historicas: list[dict]) -> list[dict]:
    clases = [d["class_id"] for d in detecciones]
    clases_historicas = [d["class_id"] for d in historicas]
    if clases != clases_historicas:
        campo = "orden" if sorted(clases) == sorted(clases_historicas) else "clase"
        return [{"campo": campo, "actual": clases, "referencia": clases_historicas}]
    if detecciones != historicas:
        firmas = [(d["class_id"], d["confidence"], *d["bbox"]) for d in detecciones]
        firmas_historicas = [(d["class_id"], d["confidence"], *d["bbox"]) for d in historicas]
        if sorted(firmas) == sorted(firmas_historicas):
            return [{"campo": "orden", "actual": detecciones, "referencia": historicas}]
    return []


def comparar_plataformas(actual: dict, referencia: dict) -> dict:
    """Registra valores y deltas; no decide una tolerancia numérica."""
    detecciones = actual["detections"]
    historicas = referencia["detections"]
    problemas = []
    for campo in ("status", "image_width", "image_height"):
        if actual[campo] != referencia[campo]:
            problemas.append(
                {"campo": campo, "actual": actual[campo], "referencia": referencia[campo]}
            )
    if len(detecciones) != len(historicas):
        problemas.append(
            {"campo": "cantidad", "actual": len(detecciones), "referencia": len(historicas)}
        )
    problemas.extend(_comparar_orden(detecciones, historicas))

    por_deteccion = []
    max_confianza = 0.0
    max_bbox = [0.0] * 4
    numerica = False
    for indice, (a, r) in enumerate(zip(detecciones, historicas, strict=False)):
        diferencia_confianza = a["confidence"] - r["confidence"]
        diferencia_bbox = [x - y for x, y in zip(a["bbox"], r["bbox"], strict=True)]
        max_confianza = max(max_confianza, abs(diferencia_confianza))
        max_bbox = [max(m, abs(d)) for m, d in zip(max_bbox, diferencia_bbox, strict=True)]
        numerica |= diferencia_confianza != 0 or any(d != 0 for d in diferencia_bbox)
        por_deteccion.append(
            {
                "indice": indice,
                "actual": a,
                "referencia": r,
                "delta_confidence": diferencia_confianza,
                "delta_bbox": diferencia_bbox,
            }
        )
    if problemas:
        clasificacion = "discrepancia_estructural"
    elif numerica:
        clasificacion = "diferencia_numerica_pendiente"
    else:
        clasificacion = "coincidencia_exacta"
    return {
        "clasificacion": clasificacion,
        "actual": {
            "status": actual["status"],
            "image_width": actual["image_width"],
            "image_height": actual["image_height"],
            "detections": detecciones,
        },
        "referencia": {
            "frame_id": referencia["frame_id"],
            "status": referencia["status"],
            "image_width": referencia["image_width"],
            "image_height": referencia["image_height"],
            "detections": historicas,
        },
        "por_deteccion": por_deteccion,
        "max_abs_delta_confidence": max_confianza,
        "max_abs_delta_bbox": max_bbox,
        "max_abs_delta_bbox_px": max(max_bbox),
        "problemas_estructurales": problemas,
    }
