import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir)))
from app.database.infrastructure.session import SessionLocal
from app.database.seed import seed_all
with SessionLocal() as db:
    n = seed_all(db)
    print(f"seeded {n} total (devices+user)")
    from app.database.infrastructure.models import DeviceORM, UserORM
    print([(d.code, d.name) for d in db.query(DeviceORM).order_by(DeviceORM.code).all()])
    print([(str(u.id), u.email) for u in db.query(UserORM).all()])
