"""API router package composition.

The application currently registers the projects router explicitly in ``api.main``.
Mount project-scoped feature routers beneath that registered router so they remain
self-contained and do not duplicate the global ``/api`` prefix.
"""

from api.routers import opportunities as opportunities
from api.routers import opportunity_monitoring as opportunity_monitoring
from api.routers import project_operator as project_operator
from api.routers import project_operator_cycle as project_operator_cycle
from api.routers import projects as projects

projects.router.include_router(opportunities.router, tags=["opportunities"])
projects.router.include_router(
    opportunity_monitoring.router,
    tags=["opportunity-monitoring"],
)
projects.router.include_router(
    project_operator.router,
    tags=["project-operator"],
)
projects.router.include_router(
    project_operator_cycle.router,
    tags=["project-operator-cycle"],
)

__all__ = [
    "opportunities",
    "opportunity_monitoring",
    "project_operator",
    "project_operator_cycle",
    "projects",
]
