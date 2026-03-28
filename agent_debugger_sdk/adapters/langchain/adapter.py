"""LangChain adapter for agent execution tracing.

This module provides the LangChainAdapter class that offers a higher-level
interface for instrumenting LangChain components with automatic context
management.
"""

from __future__ import annotations

import uuid

from agent_debugger_sdk.core.context import TraceContext

from .handler import LangChainTracingHandler


class LangChainAdapter:
    """Adapter for tracing LangChain agents and chains.

    Provides a higher-level interface for instrumenting LangChain components
    with automatic context management.

    Example:
        >>> from langchain_openai import ChatOpenAI
        >>> from agent_debugger_sdk.adapters import LangChainAdapter
        >>>
        >>> adapter = LangChainAdapter(agent_name="my_agent")
        >>> async with adapter.trace_session() as session_id:
        ...     llm = ChatOpenAI(callbacks=[adapter.handler])
        ...     result = await llm.ainvoke("Hello")
    """

    def __init__(
        self,
        session_id: str | None = None,
        agent_name: str = "",
        tags: list[str] | None = None,
    ) -> None:
        """Initialize the adapter.

        Args:
            session_id: Optional session ID. If not provided, one will be generated.
            agent_name: Human-readable name for the agent.
            tags: Optional tags for categorizing this session.
        """
        self.session_id = session_id or str(uuid.uuid4())
        self.agent_name = agent_name
        self.tags = tags or []
        self._context: TraceContext | None = None
        self._handler: LangChainTracingHandler | None = None

    @property
    def handler(self) -> LangChainTracingHandler:
        """Get the callback handler.

        Returns:
            The LangChainTracingHandler instance.
        """
        if self._handler is None:
            self._handler = LangChainTracingHandler(
                session_id=self.session_id,
                agent_name=self.agent_name,
                tags=self.tags,
            )
        return self._handler

    async def __aenter__(self) -> LangChainAdapter:
        """Enter the tracing context.

        Returns:
            The adapter instance.
        """
        self._context = TraceContext(
            session_id=self.session_id,
            agent_name=self.agent_name,
            framework="langchain",
            tags=self.tags,
        )

        await self._context.__aenter__()
        self.handler.set_context(self._context)

        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        """Exit the tracing context.

        Args:
            exc_type: Exception type if an exception was raised.
            exc_val: Exception value if an exception was raised.
            exc_tb: Exception traceback if an exception was raised.
        """
        if self._context:
            await self._context.__aexit__(exc_type, exc_val, exc_tb)

    def get_callbacks(self) -> list[LangChainTracingHandler]:
        """Get callback handlers for use with LangChain components.

        Returns:
            List containing the tracing handler.
        """
        return [self.handler]
