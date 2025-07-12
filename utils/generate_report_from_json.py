#!/usr/bin/env python3
"""
Script para generar reporte HTML desde un JSON existente
"""
import json
import sys
from disk_analyzer import DiskAnalyzer

if len(sys.argv) < 2:
    print("Uso: python generate_report_from_json.py <archivo.json>")
    sys.exit(1)

# Cargar el JSON
with open(sys.argv[1], 'r') as f:
    report = json.load(f)

# Crear instancia del analizador con path dummy
analyzer = DiskAnalyzer("/Users/aspadillar", min_size_mb=10)

# Generar el HTML
html_content = analyzer.generate_html_report(report)

# Guardar el archivo
output_file = sys.argv[1].replace('.json', '_with_tabs.html')
with open(output_file, 'w') as f:
    f.write(html_content)

print(f"✅ Reporte generado: {output_file}")