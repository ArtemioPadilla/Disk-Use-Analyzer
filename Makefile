# Makefile para macOS Disk Analyzer
# Uso: make [comando]

# Variables
PYTHON = python3
SCRIPT = disk_analyzer.py
DEFAULT_PATH = ~/
MIN_SIZE = 10
TIMESTAMP := $(shell date +%Y%m%d_%H%M%S)
REPORT_NAME = disk_report_$(TIMESTAMP)

# Colores para output
RED = \033[0;31m
GREEN = \033[0;32m
YELLOW = \033[1;33m
BLUE = \033[0;34m
NC = \033[0m # No Color

# Comandos principales
.PHONY: help analyze quick full report clean-preview clean-cache clean-docker clean-all install

help:
	@echo "$(BLUE)═══════════════════════════════════════════════════════════════$(NC)"
	@echo "$(BLUE)            macOS Disk Analyzer - Comandos Disponibles$(NC)"
	@echo "$(BLUE)═══════════════════════════════════════════════════════════════$(NC)"
	@echo ""
	@echo "$(GREEN)Análisis:$(NC)"
	@echo "  $(YELLOW)make analyze$(NC)      - Análisis estándar del directorio home"
	@echo "  $(YELLOW)make quick$(NC)        - Análisis rápido (archivos > 50MB)"
	@echo "  $(YELLOW)make full$(NC)         - Análisis completo con reporte HTML"
	@echo "  $(YELLOW)make report$(NC)       - Solo generar reporte HTML del último análisis"
	@echo ""
	@echo "$(GREEN)Limpieza:$(NC)"
	@echo "  $(YELLOW)make clean-preview$(NC) - Ver qué se puede limpiar (dry-run)"
	@echo "  $(YELLOW)make clean-cache$(NC)   - Limpiar cache del sistema"
	@echo "  $(YELLOW)make clean-docker$(NC)  - Limpiar recursos Docker"
	@echo "  $(YELLOW)make clean-all$(NC)     - Limpiar todo (cache + Docker)"
	@echo ""
	@echo "$(GREEN)Análisis específicos:$(NC)"
	@echo "  $(YELLOW)make apps$(NC)         - Analizar /Applications"
	@echo "  $(YELLOW)make downloads$(NC)    - Analizar ~/Downloads"
	@echo "  $(YELLOW)make dev$(NC)          - Analizar ~/Developer"
	@echo "  $(YELLOW)make documents$(NC)    - Analizar ~/Documents"
	@echo ""
	@echo "$(GREEN)Utilidades:$(NC)"
	@echo "  $(YELLOW)make install$(NC)      - Instalar dependencias"
	@echo "  $(YELLOW)make check$(NC)        - Verificar que todo esté instalado"
	@echo "  $(YELLOW)make open$(NC)         - Abrir el último reporte HTML"
	@echo ""
	@echo "$(BLUE)Ejemplos:$(NC)"
	@echo "  make analyze path=/Users/me/Projects"
	@echo "  make quick min_size=100"
	@echo "  make full path=/ min_size=500"
	@echo "$(BLUE)═══════════════════════════════════════════════════════════════$(NC)"

# Análisis estándar
analyze:
	@echo "$(GREEN)🔍 Iniciando análisis de disco...$(NC)"
	@$(PYTHON) $(SCRIPT) $(DEFAULT_PATH) --min-size $(MIN_SIZE)

# Análisis rápido (solo archivos grandes)
quick:
	@echo "$(GREEN)⚡ Análisis rápido (archivos > 50MB)...$(NC)"
	@$(PYTHON) $(SCRIPT) $(DEFAULT_PATH) --min-size 50

# Análisis completo con exportación
full:
	@echo "$(GREEN)📊 Análisis completo con reporte HTML...$(NC)"
	@$(PYTHON) $(SCRIPT) $(or $(path),$(DEFAULT_PATH)) --min-size $(or $(min_size),$(MIN_SIZE)) --export $(REPORT_NAME) --html
	@echo "$(GREEN)✅ Reporte generado: $(REPORT_NAME).html$(NC)"
	@echo "$(YELLOW)   Abriendo en el navegador...$(NC)"
	@open $(REPORT_NAME).html

# Generar solo reporte HTML
report:
	@echo "$(GREEN)📄 Generando reporte HTML...$(NC)"
	@$(PYTHON) $(SCRIPT) $(or $(path),$(DEFAULT_PATH)) --min-size $(or $(min_size),$(MIN_SIZE)) --export $(REPORT_NAME) --html
	@open $(REPORT_NAME).html

# Vista previa de limpieza
clean-preview:
	@echo "$(YELLOW)👀 Vista previa de limpieza (no se borrará nada)...$(NC)"
	@$(PYTHON) $(SCRIPT) $(DEFAULT_PATH) --clean-all --dry-run

# Limpiar cache
clean-cache:
	@echo "$(RED)🧹 Limpiando cache del sistema...$(NC)"
	@$(PYTHON) $(SCRIPT) $(DEFAULT_PATH) --clean-cache

# Limpiar Docker
clean-docker:
	@echo "$(RED)🐳 Limpiando recursos Docker...$(NC)"
	@$(PYTHON) $(SCRIPT) $(DEFAULT_PATH) --clean-docker

# Limpiar todo
clean-all:
	@echo "$(RED)🔥 Limpiando cache y Docker...$(NC)"
	@$(PYTHON) $(SCRIPT) $(DEFAULT_PATH) --clean-all

# Análisis de directorios específicos
apps:
	@echo "$(GREEN)📱 Analizando aplicaciones...$(NC)"
	@$(PYTHON) $(SCRIPT) /Applications --min-size 50

downloads:
	@echo "$(GREEN)📥 Analizando descargas...$(NC)"
	@$(PYTHON) $(SCRIPT) ~/Downloads --min-size 10

dev:
	@echo "$(GREEN)💻 Analizando directorio de desarrollo...$(NC)"
	@$(PYTHON) $(SCRIPT) ~/Developer --min-size 50

documents:
	@echo "$(GREEN)📄 Analizando documentos...$(NC)"
	@$(PYTHON) $(SCRIPT) ~/Documents --min-size 20

# Análisis personalizado
custom:
	@if [ -z "$(path)" ]; then \
		echo "$(RED)Error: Especifica una ruta. Ejemplo: make custom path=/ruta/a/analizar$(NC)"; \
		exit 1; \
	fi
	@echo "$(GREEN)🔍 Analizando $(path)...$(NC)"
	@$(PYTHON) $(SCRIPT) $(path) --min-size $(or $(min_size),$(MIN_SIZE))

# Verificar instalación
check:
	@echo "$(BLUE)🔍 Verificando dependencias...$(NC)"
	@echo -n "Python 3: "
	@if command -v python3 >/dev/null 2>&1; then \
		echo "$(GREEN)✓ $(shell python3 --version)$(NC)"; \
	else \
		echo "$(RED)✗ No instalado$(NC)"; \
	fi
	@echo -n "Docker: "
	@if command -v docker >/dev/null 2>&1; then \
		echo "$(GREEN)✓ $(shell docker --version | cut -d' ' -f3 | tr -d ',')$(NC)"; \
	else \
		echo "$(YELLOW)⚠ No instalado (opcional)$(NC)"; \
	fi

# Instalar dependencias (si es necesario)
install:
	@echo "$(GREEN)📦 Verificando Python...$(NC)"
	@if ! command -v python3 >/dev/null 2>&1; then \
		echo "$(RED)Python 3 no está instalado. Instálalo con: brew install python3$(NC)"; \
		exit 1; \
	fi
	@echo "$(GREEN)✅ Todo listo para usar$(NC)"

# Abrir último reporte
open:
	@LATEST=$$(ls -t disk_report_*.html 2>/dev/null | head -1); \
	if [ -z "$$LATEST" ]; then \
		echo "$(RED)No se encontraron reportes HTML$(NC)"; \
	else \
		echo "$(GREEN)Abriendo $$LATEST...$(NC)"; \
		open "$$LATEST"; \
	fi

# Limpiar reportes antiguos
clean-reports:
	@echo "$(YELLOW)🗑️  Limpiando reportes antiguos (manteniendo los últimos 5)...$(NC)"
	@ls -t disk_report_*.html 2>/dev/null | tail -n +6 | xargs -I {} rm -f {}
	@ls -t disk_report_*.json 2>/dev/null | tail -n +6 | xargs -I {} rm -f {}
	@echo "$(GREEN)✅ Reportes antiguos eliminados$(NC)"

# Estadísticas del sistema
stats:
	@echo "$(BLUE)📊 Estadísticas del Sistema$(NC)"
	@echo "$(BLUE)═══════════════════════════════════════════$(NC)"
	@echo "$(GREEN)Espacio en disco:$(NC)"
	@df -h | grep -E "^/|Filesystem"
	@echo ""
	@echo "$(GREEN)Top 5 directorios en HOME:$(NC)"
	@du -sh ~/* 2>/dev/null | sort -hr | head -5
	@if command -v docker >/dev/null 2>&1; then \
		echo ""; \
		echo "$(GREEN)Docker:$(NC)"; \
		docker system df 2>/dev/null || echo "$(YELLOW)Docker no está ejecutándose$(NC)"; \
	fi

# Comando por defecto
.DEFAULT_GOAL := help