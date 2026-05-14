#!/bin/bash
# Script para ejecutar tests automatizados en Linux/Mac
# Herramienta de Gestión Remota para Windows

echo "================================================"
echo "   Tests Automatizados - Sistema de Gestión"
echo "================================================"
echo ""

# Verificar que Python está instalado
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python3 no está instalado"
    exit 1
fi

# Verificar que pytest está instalado
if ! python3 -m pytest --version &> /dev/null; then
    echo "Instalando dependencias de testing..."
    pip3 install -r requirements-dev.txt
    if [ $? -ne 0 ]; then
        echo "ERROR: No se pudieron instalar las dependencias"
        exit 1
    fi
fi

echo "Dependencias verificadas correctamente"
echo ""

# Función para mostrar el menú
show_menu() {
    echo "Seleccione el tipo de test a ejecutar:"
    echo ""
    echo "1. Todos los tests (completo)"
    echo "2. Solo tests unitarios"
    echo "3. Solo tests de integración"
    echo "4. Tests con coverage detallado"
    echo "5. Tests rápidos (sin coverage)"
    echo "6. Tests de un módulo específico"
    echo "7. Generar reporte HTML de coverage"
    echo "8. Limpiar archivos de test"
    echo "9. Salir"
    echo ""
}

# Función para mostrar resultados
show_results() {
    echo ""
    echo "================================================"
    if [ $1 -eq 0 ]; then
        echo "   RESULTADO: TODOS LOS TESTS PASARON"
    else
        echo "   RESULTADO: ALGUNOS TESTS FALLARON"
    fi
    echo "================================================"
    echo ""
}

# Loop principal
while true; do
    show_menu
    read -p "Ingrese su opción (1-9): " option

    case $option in
        1)
            echo ""
            echo "Ejecutando TODOS los tests..."
            echo ""
            python3 -m pytest tests/ -v
            show_results $?
            ;;
        2)
            echo ""
            echo "Ejecutando tests UNITARIOS..."
            echo ""
            python3 -m pytest tests/unit/ -v -m unit
            show_results $?
            ;;
        3)
            echo ""
            echo "Ejecutando tests de INTEGRACIÓN..."
            echo ""
            python3 -m pytest tests/integration/ -v -m integration
            show_results $?
            ;;
        4)
            echo ""
            echo "Ejecutando tests con COVERAGE detallado..."
            echo ""
            python3 -m pytest tests/ -v --cov=modules --cov=utils --cov=main --cov-report=term-missing --cov-report=html
            echo ""
            echo "Reporte HTML generado en: htmlcov/index.html"
            show_results $?
            ;;
        5)
            echo ""
            echo "Ejecutando tests RÁPIDOS (sin coverage)..."
            echo ""
            python3 -m pytest tests/ -v --no-cov -x
            show_results $?
            ;;
        6)
            echo ""
            echo "Módulos disponibles:"
            echo "  - parsers"
            echo "  - cache"
            echo "  - api"
            echo "  - backup"
            echo "  - partitions"
            echo ""
            read -p "Ingrese el nombre del módulo: " module
            echo ""
            echo "Ejecutando tests de $module..."
            echo ""
            python3 -m pytest tests/ -v -k $module
            show_results $?
            ;;
        7)
            echo ""
            echo "Generando reporte HTML..."
            echo ""
            python3 -m pytest tests/ --cov=modules --cov=utils --cov=main --cov-report=html
            if [ $? -eq 0 ]; then
                echo "Reporte generado exitosamente en: htmlcov/index.html"
                # Intentar abrir en el navegador
                if command -v xdg-open &> /dev/null; then
                    xdg-open htmlcov/index.html
                elif command -v open &> /dev/null; then
                    open htmlcov/index.html
                fi
            else
                echo "ERROR: No se pudo generar el reporte"
            fi
            show_results $?
            ;;
        8)
            echo ""
            echo "Limpiando archivos de test..."
            rm -rf htmlcov .pytest_cache .coverage coverage.xml
            rm -rf **/__pycache__
            echo "Archivos limpiados correctamente"
            echo ""
            ;;
        9)
            echo ""
            echo "Finalizando tests..."
            echo ""
            exit 0
            ;;
        *)
            echo "Opción inválida"
            ;;
    esac

    read -p "¿Desea ejecutar más tests? (s/n): " continue
    if [[ ! $continue =~ ^[sS]$ ]]; then
        echo ""
        echo "Finalizando tests..."
        echo ""
        exit 0
    fi
    echo ""
done
