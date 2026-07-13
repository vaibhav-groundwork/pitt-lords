from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware

from api.config import settings
from api.db import get_connection

app = FastAPI(
    title="Pitt-Lords API",
    description="Lease compliance checklist assistant for Pittsburgh, PA landlords. "
                 "Informational tool only -- not legal advice.",
    version="0.1.0",
)

# CORS locked down to known frontend origins. Update this list as you deploy --
# never use "*" once real lease data is flowing through this API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/health")
def health_check(conn=Depends(get_connection)):
    """Confirms the API is up AND can actually reach Postgres -- not just a ping."""
    with conn.cursor() as cur:
        cur.execute("SELECT 1")
        cur.fetchone()
    return {"status": "ok", "environment": settings.environment}


# Routers land here as each phase is built:
# from api.routes import sources, leases, compliance
# app.include_router(sources.router, prefix="/sources")
# app.include_router(leases.router, prefix="/leases")
# app.include_router(compliance.router, prefix="/compliance")
