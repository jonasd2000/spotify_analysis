from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import ForeignKey, select, ForeignKeyConstraint
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

import pytest

from spotify_analysis.data.models import merge_entities

class Base(DeclarativeBase):
    pass


class ModelA(Base):
    __tablename__ = "model_a"
    a_id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    
    model_bs: Mapped[list["ModelB"]] = relationship(back_populates="model_a")

    def __repr__(self):
        return f"<ModelA(id={self.a_id}, name={self.name})>"
    
class ModelB(Base):
    __tablename__ = "model_b"
    b_id: Mapped[int] = mapped_column(primary_key=True)
    model_a_id: Mapped[int] = mapped_column(ForeignKey("model_a.a_id"))
    name: Mapped[str]
    
    model_a: Mapped[ModelA] = relationship(back_populates="model_bs")

    def __repr__(self):
        return f"<ModelB(id={self.b_id}, name={self.name})>"

class BaseCompositePK(DeclarativeBase):
    pass

class ModelACompositePK(BaseCompositePK):
    __tablename__ = "model_a_composite_pk"
    a_id1: Mapped[int] = mapped_column(primary_key=True)
    a_id2: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    
    model_bs: Mapped[list["ModelBCompositeAPK"]] = relationship(back_populates="model_a")

    def __repr__(self):
        return f"<ModelA(id1={self.a_id1}, id2={self.a_id2}, name={self.name})>"
    
class ModelBCompositeAPK(BaseCompositePK):
    __tablename__ = "model_b_composite_pk"
    b_id: Mapped[int] = mapped_column(primary_key=True)
    model_a_id1: Mapped[int] = mapped_column()
    model_a_id2: Mapped[int] = mapped_column()
    name: Mapped[str]
    __table_args__ = (
        ForeignKeyConstraint([model_a_id1, model_a_id2], ["model_a_composite_pk.a_id1", "model_a_composite_pk.a_id2"]),
        {}
    )
    
    model_a: Mapped[ModelACompositePK] = relationship(back_populates="model_bs")

    def __repr__(self):
        return f"<ModelB(id={self.b_id}, name={self.name})>"
    
    
    
@pytest.mark.asyncio
async def test_merge_entities():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    session = async_sessionmaker(engine, expire_on_commit=False)
    session = session()

    a1 = ModelA(a_id=1, name="A1")
    b1 = ModelB(name="B1", model_a=a1)
    b2 = ModelB(name="B2", model_a=a1)
    session.add_all([a1, b1, b2])
    await session.commit()
    
    a2 = ModelA(a_id=2, name="A2")
    b3 = ModelB(name="B3", model_a=a2)
    session.add_all([a2, b3])
    await session.commit()
    
    a3 = ModelA(a_id=3, name="A3")
    b4 = ModelB(name="B4", model_a=a3)
    session.add_all([a3, b4])
    await session.commit()
    
    a4 = ModelA(a_id=4, name="A4")
    session.add(a4)
    await session.commit()
    
    assert (await session.execute(select(ModelA))).scalars().all() == [a1, a2, a3, a4]
    assert (await session.execute(select(ModelB))).scalars().all() == [b1, b2, b3, b4]
    assert (await session.execute(select(ModelB).filter_by(model_a=a1))).scalars().all() == [b1, b2]
    
    await merge_entities(session, [a1, a2, a4], [ModelA, ModelB])
    assert (await session.execute(select(ModelA))).scalars().all() == [a1, a3]
    assert (await session.execute(select(ModelB))).scalars().all() == [b1, b2, b3, b4]
    assert (await session.execute(select(ModelB).filter_by(model_a=a1))).scalars().all() == [b1, b2, b3]
    
    await session.close()
    await engine.dispose()
    
@pytest.mark.asyncio
async def test_merge_entities_composite_pk():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(BaseCompositePK.metadata.drop_all)
        await conn.run_sync(BaseCompositePK.metadata.create_all)

    session = async_sessionmaker(engine, expire_on_commit=False)
    session = session()

    a1 = ModelACompositePK(a_id1=1, a_id2=1, name="A1")
    b1 = ModelBCompositeAPK(name="B1", model_a=a1)
    b2 = ModelBCompositeAPK(name="B2", model_a=a1)
    session.add_all([a1, b1, b2])
    await session.commit()
    
    a2 = ModelACompositePK(a_id1=2, a_id2=1, name="A2")
    b3 = ModelBCompositeAPK(name="B3", model_a=a2)
    session.add_all([a2, b3])
    await session.commit()
    
    a3 = ModelACompositePK(a_id1=3, a_id2=1, name="A3")
    b4 = ModelBCompositeAPK(name="B4", model_a=a3)
    session.add_all([a3, b4])
    await session.commit()
    
    assert (await session.execute(select(ModelACompositePK))).scalars().all() == [a1, a2, a3]
    assert (await session.execute(select(ModelBCompositeAPK))).scalars().all() == [b1, b2, b3, b4]
    
    await merge_entities(session, [a1, a2], [ModelBCompositeAPK])
    await session.commit()
    
    assert (await session.execute(select(ModelACompositePK))).scalars().all() == [a1, a3]
    assert (await session.execute(select(ModelBCompositeAPK))).scalars().all() == [b1, b2, b3, b4]
    assert (await session.execute(select(ModelBCompositeAPK).filter_by(model_a=a1))).scalars().all() == [b1, b2, b3]
    
    await session.close()
    await engine.dispose()