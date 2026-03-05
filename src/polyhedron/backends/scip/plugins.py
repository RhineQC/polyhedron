from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, Iterable, Optional

from polyhedron.backends.compiler import CompiledModel
from polyhedron.core.variable import Variable


@dataclass(frozen=True)
class ScipHookContext:
    model: object
    var_map: Dict[Variable, object]
    compiled: CompiledModel
    debug_hooks: Optional[list]


class ScipPlugin(ABC):
    name: str
    description: str

    @abstractmethod
    def install(self, scip_model, context: ScipHookContext) -> None:
        raise NotImplementedError


class ScipEventHandlerPlugin(ScipPlugin, ABC):
    @abstractmethod
    def build(self, pyscipopt, context: ScipHookContext):
        raise NotImplementedError

    @abstractmethod
    def event_types(self, pyscipopt) -> Iterable:
        raise NotImplementedError

    def install(self, scip_model, context: ScipHookContext) -> None:
        import pyscipopt

        handler = self.build(pyscipopt, context)
        if not hasattr(scip_model, "includeEventhdlr"):
            raise RuntimeError("SCIP model does not support event handlers.")
        scip_model.includeEventhdlr(handler, self.name, self.description)
        for event_type in self.event_types(pyscipopt):
            scip_model.catchEvent(event_type, handler)


class ScipSeparatorPlugin(ScipPlugin, ABC):
    priority: int = 0
    frequency: int = 1
    max_bound_distance: float = 1.0
    uses_subscip: bool = False
    delay: bool = False

    @abstractmethod
    def build(self, pyscipopt, context: ScipHookContext):
        raise NotImplementedError

    def install(self, scip_model, context: ScipHookContext) -> None:
        import pyscipopt

        separator = self.build(pyscipopt, context)
        if not hasattr(scip_model, "includeSepa"):
            raise RuntimeError("SCIP model does not support separators.")
        scip_model.includeSepa(
            separator,
            self.name,
            self.description,
            self.priority,
            self.frequency,
            self.max_bound_distance,
            self.uses_subscip,
            self.delay,
        )


class ScipConstraintHandlerPlugin(ScipPlugin, ABC):
    sepa_priority: int = 0
    enfo_priority: int = 0
    check_priority: int = 0
    sepa_frequency: int = 1
    prop_frequency: int = 1
    eager_frequency: int = 1
    max_prerounds: int = -1
    delay_sepa: bool = False
    delay_prop: bool = False
    needs_constraints: bool = False

    @abstractmethod
    def build(self, pyscipopt, context: ScipHookContext):
        raise NotImplementedError

    def install(self, scip_model, context: ScipHookContext) -> None:
        import pyscipopt

        handler = self.build(pyscipopt, context)
        if not hasattr(scip_model, "includeConshdlr"):
            raise RuntimeError("SCIP model does not support constraint handlers.")
        scip_model.includeConshdlr(
            handler,
            self.name,
            self.description,
            self.sepa_priority,
            self.enfo_priority,
            self.check_priority,
            self.sepa_frequency,
            self.prop_frequency,
            self.eager_frequency,
            self.max_prerounds,
            self.delay_sepa,
            self.delay_prop,
            self.needs_constraints,
        )


class ScipBranchrulePlugin(ScipPlugin, ABC):
    priority: int = 0
    max_depth: int = -1
    max_bound_distance: float = 1.0

    @abstractmethod
    def build(self, pyscipopt, context: ScipHookContext):
        raise NotImplementedError

    def install(self, scip_model, context: ScipHookContext) -> None:
        import pyscipopt

        rule = self.build(pyscipopt, context)
        if not hasattr(scip_model, "includeBranchrule"):
            raise RuntimeError("SCIP model does not support branch rules.")
        scip_model.includeBranchrule(
            rule,
            self.name,
            self.description,
            self.priority,
            self.max_depth,
            self.max_bound_distance,
        )


class ScipPricerPlugin(ScipPlugin, ABC):
    priority: int = 0
    delay: bool = False

    @abstractmethod
    def build(self, pyscipopt, context: ScipHookContext):
        raise NotImplementedError

    def install(self, scip_model, context: ScipHookContext) -> None:
        import pyscipopt

        pricer = self.build(pyscipopt, context)
        if not hasattr(scip_model, "includePricer"):
            raise RuntimeError("SCIP model does not support pricers.")
        scip_model.includePricer(
            pricer,
            self.name,
            self.description,
            self.priority,
            self.delay,
        )
