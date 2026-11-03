for s in S01 S02 S03 S04 S05 S06 S07 S08; do
  tiempos=$(grep "\"sequence_id\": \"$s\"" datos/manifiesto.jsonl \
    | sed -E 's/.*"t_relativo_ms": ([0-9]+).*/--capture-ms \1/' | tr '\n' ' ')
  uv run --locked python -m infer --input datos/cuadros/$s/ --weights modelo/descargas/yolo11n.pt \
    --output resultados/conjunto/$s/detecciones.jsonl --run-id conjunto --sequence-id $s $tiempos
done
cat resultados/conjunto/S0{1..8}/detecciones.jsonl > resultados/conjunto/conjunto.jsonl
uv run --locked python -m contrato resultados/conjunto/conjunto.jsonl
# resultados/conjunto/conjunto.jsonl: OK (107 eventos)
uv run --locked python -m metricas --detecciones resultados/conjunto/conjunto.jsonl \
  --anotaciones datos/anotaciones.jsonl --salida resultados/conjunto/metricas/ \
  --model-sha256 0ebbc80d4a7680d14987a577cd21342b65ecfd94632bd9a8da63ae6417644ee1 \
  --config-sha256 6428a259f22939fe5055dc101cec4517612dad5fb573d5852187932f39954e08
# TP=71 FP=0 FN=24 | P=1.0000 R=0.7474 F1=0.8554 | 1.4: 5/6
