from sqlalchemy import Column, DateTime, Float, Integer, String, Text, func
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


DATABASE_URL = "sqlite+aiosqlite:///./translator.db"

engine = create_async_engine(DATABASE_URL, echo=False)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Problem(Base):
    __tablename__ = "problems"

    id = Column(Integer, primary_key=True, autoincrement=True)
    difficulty = Column(String(10), nullable=False)
    category = Column(String(30), nullable=False, default="arrays")
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=False)
    typescript_code = Column(Text, nullable=False)
    python_solution = Column(Text, nullable=False)
    test_cases = Column(Text, nullable=False)  # JSON string
    example_input = Column(Text, nullable=False)
    example_output = Column(Text, nullable=False)
    custom_subject = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())


class Submission(Base):
    __tablename__ = "submissions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    problem_id = Column(Integer, nullable=False)
    user_code = Column(Text, nullable=False)
    correctness_score = Column(Float, default=0.0)
    ast_score = Column(Float, default=0.0)
    llm_score = Column(Float, default=0.0)
    overall_score = Column(Float, default=0.0)
    feedback = Column(Text, default="")
    created_at = Column(DateTime, server_default=func.now())


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncSession:  # type: ignore[misc]
    async with async_session() as session:
        yield session
