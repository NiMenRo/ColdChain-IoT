from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from simulator.config.simulator_config import SimulatorConfig

_config = SimulatorConfig()
engine = create_engine(_config.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
