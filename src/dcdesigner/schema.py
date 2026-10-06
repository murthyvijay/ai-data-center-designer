"""Input schema for a design.

A design spec is the only input to the compiler. It names catalog items by id
and carries the handful of architectural choices that matter at each tier.
Everything else is derived, so the same spec always compiles to the same
design.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class NodeSpec(_Strict):
    """Tier 2: the node (an 8-GPU server, or a compute tray in a rack-scale system)."""

    name: str
    form: Literal["tray", "server"]
    accelerator: str
    accelerators: int = Field(gt=0)
    nic: str
    nics: int = Field(gt=0)
    rack_units: int = Field(gt=0)
    components: dict[str, int] = Field(default_factory=dict)


class SwitchTraySpec(_Strict):
    name: str
    per_domain: int = Field(gt=0)
    rack_units: int = Field(gt=0)
    components: dict[str, int]


class ScaleUpSpec(_Strict):
    """Scale-up (L1/L2 memory-semantic) domain: NVLink or UALink."""

    technology: str
    domain: Literal["node", "rack"]
    gpus_per_domain: int = Field(gt=0)
    gbytes_s_per_gpu: float = Field(gt=0)
    medium: str
    switch_tray: SwitchTraySpec | None = None


class RackSpec(_Strict):
    """Tier 3: the mechanical, thermal and electrical boundary."""

    name: str
    nodes: int = Field(gt=0)
    frame: str
    rack_units: int = 48
    components: dict[str, int] = Field(default_factory=dict)
    power_shelf: str
    power_shelf_spares: int = Field(default=1, ge=0)
    power_budget_kw: float = Field(gt=0)
    cooling: Literal["liquid", "hybrid", "air"]
    liquid_fraction: float = Field(ge=0, le=1)


class ScaleOutSpec(_Strict):
    """Scale-out RoCE fabric: rail-optimized folded Clos."""

    switch: str
    nic_gbps: int = Field(gt=0)
    planes: int = Field(default=1, gt=0)
    oversubscription: float = Field(default=1.0, ge=1.0)
    rails: int = Field(gt=0)
    su_racks: int = Field(gt=0)
    sus_per_superpod: int = Field(gt=0)
    allowed_media: list[Literal["dac", "aec", "lpo", "dr", "fr"]] = Field(
        default_factory=lambda: ["dac", "aec", "lpo", "dr", "fr"]
    )
    mtu: int = 9216
    roce_priority: int = Field(default=3, ge=0, le=7)


class LayoutSpec(_Strict):
    """Geometry used to estimate cable lengths, and so pick link media."""

    rack_width_m: float = 0.6
    row_pitch_m: float = 3.0
    vertical_m: float = 1.5  # rise from a port to the overhead tray, per end
    row_slack_m: float = 1.0  # service loop on in-row runs
    tray_slack_m: float = 3.0  # routing slack on inter-row and inter-hall runs
    network_rack_ru: int = 42
    hall_spacing_m: float = 150.0
    hall_to_core_m: float = 60.0


class FacilitySpec(_Strict):
    hall_it_mw_max: float = Field(gt=0)
    pue: float = Field(default=1.2, ge=1.0)
    cdu_spares_per_hall: int = 1
    wan_edge_routers: int = 4


class DesignSpec(_Strict):
    name: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    title: str
    architecture: str
    description: str = ""
    gpu_target: int = Field(gt=0)
    node: NodeSpec
    scale_up: ScaleUpSpec
    rack: RackSpec
    scale_out: ScaleOutSpec
    layout: LayoutSpec = LayoutSpec()
    facility: FacilitySpec
    nos: list[Literal["sonic", "eos", "nxos"]] = Field(default_factory=lambda: ["sonic", "eos", "nxos"])

    @property
    def gpus_per_rack(self) -> int:
        return self.rack.nodes * self.node.accelerators

    @model_validator(mode="after")
    def _check(self) -> DesignSpec:
        gpr = self.gpus_per_rack
        if self.node.nics != self.node.accelerators:
            raise ValueError("scale-out model assumes one NIC per accelerator (node.nics == node.accelerators)")
        if self.scale_up.domain == "rack" and self.scale_up.gpus_per_domain != gpr:
            raise ValueError(f"rack-scale scale-up domain must equal GPUs per rack ({gpr})")
        if self.scale_up.domain == "node" and self.scale_up.gpus_per_domain != self.node.accelerators:
            raise ValueError("node-scale scale-up domain must equal accelerators per node")
        if gpr % self.scale_out.rails:
            raise ValueError(f"GPUs per rack ({gpr}) must divide evenly into {self.scale_out.rails} rails")
        if self.scale_out.nic_gbps % self.scale_out.planes:
            raise ValueError("nic_gbps must divide evenly across planes")
        if self.scale_up.switch_tray and self.scale_up.domain != "rack":
            raise ValueError("a separate scale-up switch tray only applies to a rack-scale domain")
        return self
