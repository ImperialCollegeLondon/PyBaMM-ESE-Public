#
# Function to create battery geometries
#
import pybamm


def battery_geometry(
    include_particles=True,
    options=None,
    current_collector_dimension=0,
    form_factor="pouch",
):
    """
    A convenience function to create battery geometries.

    Parameters
    ----------
    include_particles : bool, optional
        Whether to include particle domains. Can be True (default) or False.
    options : dict, optional
        Dictionary of model options. Necessary for "particle-size geometry",
        relevant for lithium-ion chemistries.
    current_collector_dimensions : int, optional
        The dimensions of the current collector. Can be 0 (default), 1 or 2. For
        a "cylindrical" form factor the current collector dimension must be 0 or 1.
    form_factor : str, optional
        The form factor of the cell. Can be "pouch" (default) or "cylindrical".

    Returns
    -------
    :class:`pybamm.Geometry`
        A geometry class for the battery

    """
    options = pybamm.BatteryModelOptions(options or {})
    geo = pybamm.GeometricParameters(options)
    L_n = geo.n.L
    L_s = geo.s.L
    L_n_L_s = L_n + L_s
    # Override print_name
    L_n_L_s.print_name = "L_n + L_s"

    # Set up electrode/separator/electrode geometry
    geometry = {
        "negative electrode": {"x_n": {"min": 0, "max": L_n}},
        "separator": {"x_s": {"min": L_n, "max": L_n_L_s}},
        "positive electrode": {"x_p": {"min": L_n_L_s, "max": geo.L_x}},
    }
    # Add particle domains
    if include_particles is True:
        for domain in ["negative", "positive"]:
            if options.electrode_types[domain] == "planar":
                continue
            geo_domain = geo.domain_params[domain]
            d = domain[0]
            geometry.update(
                {
                    f"{domain} particle": {
                        f"r_{d}": {"min": 0, "max": geo_domain.prim.R_typ}
                    },
                }
            )
            phases = int(getattr(options, domain)["particle phases"])
            if phases >= 2:
                geometry.update(
                    {
                        f"{domain} primary particle": {
                            f"r_{d}_prim": {"min": 0, "max": geo_domain.prim.R_typ}
                        },
                        f"{domain} secondary particle": {
                            f"r_{d}_sec": {"min": 0, "max": geo_domain.sec.R_typ}
                        },
                    }
                )
    # Add particle size domains
    if options is not None and options["particle size"] == "distribution":
        R_min_n = geo.n.prim.R_min
        R_min_p = geo.p.prim.R_min
        R_max_n = geo.n.prim.R_max
        R_max_p = geo.p.prim.R_max
        geometry.update(
            {
                "negative particle size": {"R_n": {"min": R_min_n, "max": R_max_n}},
                "positive particle size": {"R_p": {"min": R_min_p, "max": R_max_p}},
            }
        )
    # Add current collector domains
    if form_factor == "pouch":
        if current_collector_dimension == 0:
            geometry["current collector"] = {"z": {"position": 1}}
        elif current_collector_dimension == 1:
            geometry["current collector"] = {
                "z": {"min": 0, "max": geo.L_z},
                "tabs": {
                    "negative": {"z_centre": geo.n.centre_z_tab},
                    "positive": {"z_centre": geo.p.centre_z_tab},
                },
            }
        elif current_collector_dimension == 2:
            geometry["current collector"] = {
                "y": {"min": 0, "max": geo.L_y},
                "z": {"min": 0, "max": geo.L_z},
                "tabs": {
                    "negative": {
                        "y_centre": geo.n.centre_y_tab,
                        "z_centre": geo.n.centre_z_tab,
                        "width": geo.n.L_tab,
                    },
                    "positive": {
                        "y_centre": geo.p.centre_y_tab,
                        "z_centre": geo.p.centre_z_tab,
                        "width": geo.p.L_tab,
                    },
                },
            }
        else:
            raise pybamm.GeometryError(
                "Invalid current collector dimension '{}' (should be 0, 1 or 2)".format(
                    current_collector_dimension
                )
            )
    elif form_factor == "cylindrical":
        if current_collector_dimension == 0:
            geometry["current collector"] = {"r_macro": {"position": 1}}
        elif current_collector_dimension == 1:
            geometry["current collector"] = {
                "r_macro": {"min": geo.r_inner, "max": 1},
            }
        else:
            raise pybamm.GeometryError(
                "Invalid current collector dimension '{}' (should be 0 or 1 for "
                "a 'cylindrical' battery geometry)".format(current_collector_dimension)
            )
    else:
        raise pybamm.GeometryError(
            "Invalid form factor '{}' (should be 'pouch' or 'cylindrical'".format(
                form_factor
            )
        )

    return pybamm.Geometry(geometry)
