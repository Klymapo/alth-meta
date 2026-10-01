# COPOX · Research preflight

Regla productiva: **ninguna mutación nueva arranca sin research previo documentado**.

El research ocurre después de elegir el módulo/objetivo y antes de modificar geometría. Debe comprobar si ya existen técnicas conocidas para conseguir el resultado buscado, priorizando documentación oficial y complementándola con fuentes técnicas de comunidad cuando aporte experiencia práctica.

Cada brief `copox/research/<module>.json` debe incluir:

- objetivo técnico concreto;
- fecha de investigación;
- al menos dos fuentes web con URL y hallazgo relevante;
- técnicas encontradas y si aplican o no al caso;
- dirección elegida y riesgos/limitaciones;
- una entrada por `technique_round` que el loop pretenda ejecutar.

`copox.production.research_gate` bloquea la mutación si falta el brief, está viejo, no hubo consulta de internet, no hay fuentes suficientes o la técnica de esa ronda no fue investigada.

Esto **no ejecuta código copiado de internet**. Las fuentes sirven para orientar la técnica; la implementación sigue siendo propia, auditable y sometida a los gates de COPOX.

Para mantener costo cero, la búsqueda y síntesis la realiza el director antes de habilitar una nueva técnica; GitHub Actions sólo verifica el brief y se niega a mutar si no existe evidencia de research.
