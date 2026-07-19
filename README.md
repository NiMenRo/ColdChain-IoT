# ColdChain-IoT

ColdChain-IoT es un sistema de monitoreo IoT orientado a la supervisión de cavas y vitrinas refrigeradas mediante sensores virtuales de temperatura, humedad y estado energético. El proyecto implementa un modelo de priorización de tráfico IoT para clasificar las lecturas según su nivel de criticidad y evaluar el impacto de diferentes estrategias de planificación sobre las métricas de Calidad de Servicio (QoS).

El sistema simula el funcionamiento de una infraestructura IoT completa, desde la generación de datos por parte de dispositivos virtuales hasta su transmisión mediante MQTT, procesamiento en un backend desarrollado con FastAPI, almacenamiento en PostgreSQL y visualización en una plataforma web desarrollada con React.

## Objetivos

- Simular dispositivos IoT para cavas y vitrinas refrigeradas.
- Monitorear variables ambientales en tiempo real.
- Clasificar las lecturas según su nivel de prioridad.
- Evaluar algoritmos de planificación de tráfico (FIFO, Round Robin y WFQ).
- Analizar métricas de Calidad de Servicio (QoS) como latencia, jitter, throughput y Packet Delivery Ratio (PDR).
- Visualizar el comportamiento del sistema mediante un dashboard web interactivo.

## Stack tecnológico

### Backend
- Python
- FastAPI
- PostgreSQL
- MQTT

### Frontend
- React
- Bootstrap

### Simulación
- Python
- MQTT

### Herramientas
- Git
- GitHub
- Docker

## Arquitectura

El proyecto está organizado como un **monorepositorio** compuesto por tres aplicaciones independientes:

```text
backend/
    API REST, procesamiento de datos y lógica de negocio.

frontend/
    Interfaz web para monitoreo y visualización.

simulator/
    Generación de dispositivos IoT y sensores virtuales.
```

El backend sigue una arquitectura modular basada en dominios (Feature-Based Architecture), inspirada en Clean Architecture, permitiendo mantener cada módulo desacoplado y facilitando la escalabilidad del sistema.

## Estado del proyecto

--> En desarrollo.

Actualmente el proyecto se encuentra en la fase de implementación del prototipo correspondiente al Trabajo de Grado.

## Licencia

Proyecto desarrollado con fines académicos.