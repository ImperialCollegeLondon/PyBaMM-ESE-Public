#
# Doyle-Fuller-Newman (DFN) Model
#
import pybamm
from .base_lithium_ion_model import BaseModel


class DFN(BaseModel):
    """
    Doyle-Fuller-Newman (DFN) model of a lithium-ion battery, from [1]_.

    Parameters
    ----------
    options : dict, optional
        A dictionary of options to be passed to the model. For a detailed list of
        options see :class:`~pybamm.BatteryModelOptions`.
    name : str, optional
        The name of the model.
    build :  bool, optional
        Whether to build the model on instantiation. Default is True. Setting this
        option to False allows users to change any number of the submodels before
        building the complete model (submodels cannot be changed after the model is
        built).
    Examples
    --------
    >>> import pybamm
    >>> model = pybamm.lithium_ion.DFN()
    >>> model.name
    'Doyle-Fuller-Newman model'

    References
    ----------
    .. [1] SG Marquis, V Sulzer, R Timms, CP Please and SJ Chapman. “An asymptotic
           derivation of a single particle model with electrolyte”. Journal of The
           Electrochemical Society, 166(15):A3693–A3706, 2019


    **Extends:** :class:`pybamm.lithium_ion.BaseModel`
    """

    def __init__(self, options=None, name="Doyle-Fuller-Newman model", build=True):
        # For degradation models we use the full form since this is a full-order model
        self.x_average = False
        super().__init__(options, name)

        self.set_submodels(build)

        pybamm.citations.register("Doyle1993")

    def set_convection_submodel(self):

        self.submodels[
            "transverse convection"
        ] = pybamm.convection.transverse.NoConvection(self.param, self.options)
        self.submodels[
            "through-cell convection"
        ] = pybamm.convection.through_cell.NoConvection(self.param, self.options)

    def set_intercalation_kinetics_submodel(self):
        for domain in ["negative", "positive"]:
            electrode_type = self.options.electrode_types[domain]
            if electrode_type == "porous":
                intercalation_kinetics = self.get_intercalation_kinetics(domain)
                phases = self.options.phases[domain]
                for phase in phases:
                    submod = intercalation_kinetics(
                        self.param, domain, "lithium-ion main", self.options, phase
                    )
                    self.submodels[f"{domain} {phase} interface"] = submod

                if len(phases) > 1:
                    self.submodels[
                        f"total {domain} interface"
                    ] = pybamm.kinetics.TotalMainKinetics(
                        self.param, domain, "lithium-ion main", self.options
                    )

    def set_particle_submodel(self):
        for domain in ["negative", "positive"]:
            if self.options.electrode_types[domain] == "planar":
                continue
            particle = getattr(self.options, domain)["particle"]
            for phase in self.options.phases[domain]:
                if particle == "Fickian diffusion":
                    submod = pybamm.particle.FickianDiffusion(
                        self.param, domain, self.options, phase=phase, x_average=False
                    )
                elif particle in [
                    "uniform profile",
                    "quadratic profile",
                    "quartic profile",
                ]:
                    submod = pybamm.particle.PolynomialProfile(
                        self.param, domain, self.options, phase=phase
                    )
                self.submodels[f"{domain} {phase} particle"] = submod

    def set_solid_submodel(self):
        for domain in ["negative", "positive"]:
            if self.options.electrode_types[domain] == "planar":
                continue
            if self.options["surface form"] == "false":
                submodel = pybamm.electrode.ohm.Full
            else:
                submodel = pybamm.electrode.ohm.SurfaceForm
            self.submodels[f"{domain} electrode potential"] = submodel(
                self.param, domain, self.options
            )

    def set_electrolyte_concentration_submodel(self):
        self.submodels["electrolyte diffusion"] = pybamm.electrolyte_diffusion.Full(
            self.param, self.options
        )

    def set_electrolyte_potential_submodel(self):
        surf_form = pybamm.electrolyte_conductivity.surface_potential_form

        if self.options["electrolyte conductivity"] not in ["default", "full","sol full"]:
            raise pybamm.OptionError(
                "electrolyte conductivity '{}' not suitable for DFN".format(
                    self.options["electrolyte conductivity"]
                )
            )

        if self.options["surface form"] == "false":
            if self.options["electrolyte conductivity"] == "sol full":
                self.submodels[
                    "electrolyte conductivity"
                ] = pybamm.electrolyte_conductivity.sol_Full(self.param, self.options)
            if self.options["electrolyte conductivity"] == "full":
                self.submodels[
                    "electrolyte conductivity"
                ] = pybamm.electrolyte_conductivity.Full(self.param, self.options)

        if self.options["surface form"] == "false":
            surf_model = surf_form.Explicit
        elif self.options["surface form"] == "differential":
            surf_model = surf_form.FullDifferential
        elif self.options["surface form"] == "algebraic":
            surf_model = surf_form.FullAlgebraic

        for domain in ["negative", "separator", "positive"]:
            if self.options.electrode_types.get(domain) == "planar":
                continue
            self.submodels[f"{domain} surface potential difference"] = surf_model(
                self.param, domain, self.options
            )
    

    # Mark Ruihe block start
    def set_solvent_diffusion_submodel(self): # Mark Ruihe Li modify
        if self.options["solvent diffusion"] == "double spatial consume w refill":
            self.submodels[
                "solvent diffusion"
            ] = pybamm.solvent_diffusion.Double_SpatialConsume_w_refill(self.param, self.options)
        elif self.options["solvent diffusion"] == "double spatial consume wo refill":
            self.submodels[
                "solvent diffusion"
            ] = pybamm.solvent_diffusion.Double_SpatialConsume_wo_refill(self.param, self.options)
        elif self.options["solvent diffusion"] == "single no consume wo refill":
            self.submodels[
                "solvent diffusion"
            ] = pybamm.solvent_diffusion.Single_NoConsume_wo_refill(self.param, self.options)
        elif self.options["solvent diffusion"] == "single spatial consume w refill":
            self.submodels[
                "solvent diffusion"
            ] = pybamm.solvent_diffusion.Single_SpatialConsume_w_refill(self.param, self.options)
        elif self.options["solvent diffusion"] == "single spatial consume wo refill":
            self.submodels[
                "solvent diffusion"
            ] = pybamm.solvent_diffusion.Single_SpatialConsume_wo_refill(self.param, self.options)
    # Mark Ruihe block end