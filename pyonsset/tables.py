"""
Contains functions to calculate LCOEs and number of people required for grid.
"""

import logging
import numpy as np
import pandas as pd
from math import ceil, sqrt
from pyonsset.constants import *

logging.basicConfig(format='%(asctime)s\t\t%(message)s', level=logging.DEBUG)


def make_tables(scenario, specs_xlsx=FF_SPECS):
    """
    Create the LCOES and capital costs for grid and each technology, as well as the number of people required to be
    grid-connected, for each set of parameters.

    @param scenario: the scenario value in kWh/hh/year
    @param specs_xlsx: the specs file containing the country specific parameters
    """

    logging.info('Starting function tables.make_tables()')

    output_dir = os.path.join(FF_LCOES, str(scenario))
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # Import country specific values from Excel
    specs = pd.read_excel(specs_xlsx)[[SPE_COUNTRY, SPE_GRID_PRICE, SPE_GRID_LOSSES,
                                       SPE_BASE_TO_PEAK, SPE_DIESEL_PRICE_LOW]]

    # From 10 to 4000 people per km2
    # techs must be modified if any new technologies are added
    people_arr = [10 * x for x in range(1, 401)]
    techs = [MG_HYDRO, MG_PV_LOW, MG_PV_HIGH, MG_WIND_LOW, MG_WIND_MID,
             MG_WIND_HIGH, MG_DIESEL, SA_DIESEL, SA_PV_LOW, SA_PV_HIGH]

    # A pd.Panel for each of the main results
    grid_lcoes = pd.Panel(np.zeros([len(specs), len(ELEC_DISTANCES), len(people_arr)]),
                          items=specs[SPE_COUNTRY].values, major_axis=ELEC_DISTANCES, minor_axis=people_arr)
    grid_cap = pd.Panel(np.zeros([len(specs), len(ELEC_DISTANCES), len(people_arr)]),
                        items=specs[SPE_COUNTRY].values, major_axis=ELEC_DISTANCES, minor_axis=people_arr)
    tech_lcoes = pd.Panel(np.zeros([len(specs), len(techs), len(people_arr)]),
                          items=specs[SPE_COUNTRY].values, major_axis=techs, minor_axis=people_arr)
    tech_cap = pd.Panel(np.zeros([len(specs), len(techs), len(people_arr)]),
                        items=specs[SPE_COUNTRY].values, major_axis=techs, minor_axis=people_arr)

    for index, country_specs in specs.iterrows():
        country_name = country_specs[SPE_COUNTRY]
        for people in people_arr:

            # First calculate the full LCOE values, and insert the results into the panels
            lcoes = get_lcoes(country_specs, people, scenario, False)
            grid_lcoes[country_name][people] = lcoes[GRID]
            tech_lcoes[country_name][people][MG_HYDRO] = lcoes[MG_HYDRO]
            tech_lcoes[country_name][people][MG_PV_LOW] = lcoes[MG_PV_LOW]
            tech_lcoes[country_name][people][MG_PV_HIGH] = lcoes[MG_PV_HIGH]
            tech_lcoes[country_name][people][MG_WIND_LOW] = lcoes[MG_WIND_LOW]
            tech_lcoes[country_name][people][MG_WIND_MID] = lcoes[MG_WIND_MID]
            tech_lcoes[country_name][people][MG_WIND_HIGH] = lcoes[MG_WIND_HIGH]
            tech_lcoes[country_name][people][MG_DIESEL] = lcoes[MG_DIESEL]
            tech_lcoes[country_name][people][SA_DIESEL] = lcoes[SA_DIESEL]
            tech_lcoes[country_name][people][SA_PV_LOW] = lcoes[SA_PV_LOW]
            tech_lcoes[country_name][people][SA_PV_HIGH] = lcoes[SA_PV_HIGH]

            # Then calculate only the capital costs, and insert the values
            lcoes = get_lcoes(country_specs, people, scenario, True)
            grid_cap[country_name][people] = lcoes[GRID]
            tech_cap[country_name][people][MG_HYDRO] = lcoes[MG_HYDRO]
            tech_cap[country_name][people][MG_PV_LOW] = lcoes[MG_PV_LOW]
            tech_cap[country_name][people][MG_PV_HIGH] = lcoes[MG_PV_HIGH]
            tech_cap[country_name][people][MG_WIND_LOW] = lcoes[MG_WIND_LOW]
            tech_cap[country_name][people][MG_WIND_MID] = lcoes[MG_WIND_MID]
            tech_cap[country_name][people][MG_WIND_HIGH] = lcoes[MG_WIND_HIGH]
            tech_cap[country_name][people][MG_DIESEL] = lcoes[MG_DIESEL]
            tech_cap[country_name][people][SA_DIESEL] = lcoes[SA_DIESEL]
            tech_cap[country_name][people][SA_PV_LOW] = lcoes[SA_PV_LOW]
            tech_cap[country_name][people][SA_PV_HIGH] = lcoes[SA_PV_HIGH]

    # Save the panels to csv
    grid_lcoes.transpose(2, 0, 1).to_frame().to_csv(FF_GRID_LCOES(scenario))
    grid_cap.transpose(2, 0, 1).to_frame().to_csv(FF_GRID_CAP(scenario))
    tech_lcoes.transpose(2, 0, 1).to_frame().to_csv(FF_TECH_LCOES(scenario))
    tech_cap.transpose(2, 0, 1).to_frame().to_csv(FF_TECH_CAP(scenario))

    # The following section calculates the number of people required before grid-connecting is feasible
    # Dependent on country and distance from existing grid

    # The dataframe is initialised with very high default values
    num_people_for_grid = pd.DataFrame(1e9 * np.ones([len(ELEC_DISTANCES), len(specs)]), index=ELEC_DISTANCES,
                                       columns=specs[SPE_COUNTRY].values)

    # Loop through every comination of variables and see at what point (number of people) the grid becomes the
    # most economical option.
    for country in grid_lcoes:
        for additional_mv_line_length in ELEC_DISTANCES:
            for people in people_arr:
                lcoes = tech_lcoes[country][people]
                # TODO This check excludes some technologies, why?
                min_lcoe_techs = min(lcoes[MG_DIESEL], lcoes[MG_WIND_MID],
                                     (lcoes[SA_PV_LOW] + lcoes[SA_PV_HIGH]) / 2,
                                     lcoes[MG_HYDRO])

                if grid_lcoes[country][people][additional_mv_line_length] < min_lcoe_techs:
                    num_people_for_grid[country][additional_mv_line_length] = people
                    break

    num_people_for_grid.to_csv(FF_NUM_PEOPLE(scenario))

    logging.info('Completed function tables.make_tables()')


def get_lcoes(country_specs, people, scenario, calc_cap_only):
    """

    @param country_specs: a Series containing country-specific data
    @param people: the number of people for this iteration
    @param scenario: the scenario, kWh/hh/year
    @param calc_cap_only: # whether to calculate capital cost only, or include full LCOE
    @return: a dictionary containing the LCOE for each technology pathway
    """
    transmission_losses = float(country_specs[SPE_GRID_LOSSES])
    base_to_peak_load_ratio = float(country_specs[SPE_BASE_TO_PEAK])
    grid_price = float(country_specs[SPE_GRID_PRICE])
    diesel_price = float(country_specs[SPE_DIESEL_PRICE_LOW]) / LHV_DIESEL  # to convert from USD/L to USD/kWh
    om_of_td_lines = 0.03 # percentage (kept here so that it can be specified differently for lcoe/cap_only options)

    # All O&M and fuel costs are excluded if we're calculating capital costs only
    if calc_cap_only:
        om_of_td_lines = 0
        grid_price = 0
        diesel_price = 0

    lcoes = {}

    # Each technology gets a call to calc_lcoe() with the relevant parameters
    # The grid calculation is a list comprehension including lcoes for each value in ELEC_DISTANCES
    lcoes[GRID] = [calc_lcoe(people=people,
                             scenario=scenario,
                             om_of_td_lines=om_of_td_lines,
                             distribution_losses=transmission_losses,
                             connection_cost_per_hh=125,
                             base_to_peak_load_ratio=base_to_peak_load_ratio,
                             system_life=30,
                             additional_mv_line_length=additional_mv_line_length,
                             grid_price=grid_price,
                             grid=True)
                   for additional_mv_line_length in ELEC_DISTANCES]

    # mg_hydro
    om_costs = 0 if calc_cap_only else 0.02
    lcoes[MG_HYDRO] = calc_lcoe(people=people,
                                scenario=scenario,
                                om_of_td_lines=om_of_td_lines,
                                capacity_factor=0.5,
                                distribution_losses=0.05,
                                connection_cost_per_hh=100,
                                capital_cost=5000,
                                om_costs=om_costs,
                                base_to_peak_load_ratio=1.0,
                                system_life=30,
                                mv_line_length=5)

    # mg_pv1750
    irradiation = 1750.0
    om_costs = 0 if calc_cap_only else 0.02
    lcoes[MG_PV_LOW] = calc_lcoe(people=people,
                                 scenario=scenario,
                                 om_of_td_lines=om_of_td_lines,
                                 capacity_factor=irradiation / HOURS_PER_YEAR,
                                 distribution_losses=0.05,
                                 connection_cost_per_hh=100,
                                 capital_cost=4300,
                                 om_costs=om_costs,
                                 base_to_peak_load_ratio=0.9,
                                 system_life=20)

    # mg_pv2250
    irradiation = 2250
    om_costs = 0 if calc_cap_only else 0.02
    lcoes[MG_PV_HIGH] = calc_lcoe(people=people,
                                  scenario=scenario,
                                  om_of_td_lines=om_of_td_lines,
                                  capacity_factor=irradiation / HOURS_PER_YEAR,
                                  distribution_losses=0.05,
                                  connection_cost_per_hh=100,
                                  capital_cost=4300,
                                  om_costs=om_costs,
                                  base_to_peak_load_ratio=0.9,
                                  system_life=20)

    # mg_wind0.2
    om_costs = 0 if calc_cap_only else 0.02
    lcoes[MG_WIND_LOW] = calc_lcoe(people=people,
                                   scenario=scenario,
                                   om_of_td_lines=om_of_td_lines,
                                   capacity_factor=0.2,
                                   distribution_losses=0.05,
                                   connection_cost_per_hh=100,
                                   capital_cost=3000,
                                   om_costs=om_costs,
                                   base_to_peak_load_ratio=0.75,
                                   system_life=20)

    # mg_wind0.3
    om_costs = 0 if calc_cap_only else 0.02
    lcoes[MG_WIND_MID] = calc_lcoe(people=people,
                                   scenario=scenario,
                                   om_of_td_lines=om_of_td_lines,
                                   capacity_factor=0.3,
                                   distribution_losses=0.05,
                                   connection_cost_per_hh=100,
                                   capital_cost=3000,
                                   om_costs=om_costs,
                                   base_to_peak_load_ratio=0.75,
                                   system_life=20)

    # mg_wind0.4
    om_costs = 0 if calc_cap_only else 0.02
    lcoes[MG_WIND_HIGH] = calc_lcoe(people=people,
                                    scenario=scenario,
                                    om_of_td_lines=om_of_td_lines,
                                    capacity_factor=0.4,
                                    distribution_losses=0.05,
                                    connection_cost_per_hh=100,
                                    capital_cost=3000,
                                    om_costs=om_costs,
                                    base_to_peak_load_ratio=0.75,
                                    system_life=20)

    # mg_diesel
    om_costs = 0 if calc_cap_only else 0.1
    lcoes[MG_DIESEL] = calc_lcoe(people=people,
                                 scenario=scenario,
                                 om_of_td_lines=om_of_td_lines,
                                 capacity_factor=0.7,
                                 distribution_losses=0.05,
                                 connection_cost_per_hh=100,
                                 capital_cost=721,
                                 om_costs=om_costs,
                                 base_to_peak_load_ratio=0.5,
                                 system_life=15,
                                 efficiency=0.33,
                                 diesel_price=diesel_price,
                                 diesel=True)

    # sa_diesel
    om_costs = 0 if calc_cap_only else 0.1
    lcoes[SA_DIESEL] = calc_lcoe(people=people,
                                 scenario=scenario,
                                 om_of_td_lines=0,
                                 capacity_factor=0.7,
                                 distribution_losses=0,
                                 connection_cost_per_hh=100,
                                 capital_cost=721,
                                 om_costs=om_costs,
                                 base_to_peak_load_ratio=0.5,
                                 system_life=15,
                                 efficiency=0.33,
                                 diesel_price=diesel_price,
                                 diesel=True,
                                 standalone=True)

    # sa_pv1750
    irradiation = 1750
    om_costs = 0 if calc_cap_only else 0.02
    lcoes[SA_PV_LOW] = calc_lcoe(people=people,
                                 scenario=scenario,
                                 om_of_td_lines=0,
                                 capacity_factor=irradiation / HOURS_PER_YEAR,
                                 distribution_losses=0,
                                 connection_cost_per_hh=100,
                                 capital_cost=4300,
                                 om_costs=om_costs,
                                 base_to_peak_load_ratio=0.9,
                                 system_life=20,
                                 standalone=True)

    # sa_pv2250
    irradiation = 2250
    om_costs = 0 if calc_cap_only else 0.02
    lcoes[SA_PV_HIGH] = calc_lcoe(people=people,
                                  scenario=scenario,
                                  om_of_td_lines=0,
                                  capacity_factor=irradiation / HOURS_PER_YEAR,
                                  distribution_losses=0,
                                  connection_cost_per_hh=100,
                                  capital_cost=4300,
                                  om_costs=om_costs,
                                  base_to_peak_load_ratio=0.9,
                                  system_life=20,
                                  standalone=True)

    return lcoes


def calc_lcoe(people, scenario, om_of_td_lines, distribution_losses, connection_cost_per_hh,
              base_to_peak_load_ratio, system_life, mv_line_length=0, om_costs=0.0, capital_cost=0, capacity_factor=1.0,
              efficiency=1.0, diesel_price=0, additional_mv_line_length=0, grid_price=0, grid=False, diesel=False,
              standalone=False):
    """
    Calculate the LCOE for a single technology with a single people/distance pair.

    @param people: the number of people
    @param scenario: the scenario value, in kWh/hh/year
    @param om_of_td_lines: the O&M cost of TD lines as a percentage of investment cost
    @param distribution_losses: as a percentage
    @param connection_cost_per_hh: USD, cost to connect a household to a specific technology
    @param base_to_peak_load_ratio: as a percentage
    @param system_life: in years
    @param mv_line_length: the MV line length in km needed to connect minigrid technologies
    @param om_costs: O&M costs of a technology as a percentage of capital cost (non-grid only)
    @param capital_cost: USD/kW (non-grid only)
    @param capacity_factor: percentage (non-grid only)
    @param efficiency: percentage (diesel only)
    @param diesel_price: USD/kWh (diesel only)
    @param additional_mv_line_length: the additional MV line length in km, from ELEC_DISTANCES (grid only)
    @param grid_price: USD/kWh (grid only)
    @param grid: True/False flag for grid
    @param diesel: True/False flag for diesel
    @param standalone: True/False flag for standalone
    @return: The LCOE values with the given parameters
    """

    grid_cell_area = 100 # TODO This should be fixed to 1, but some values and calculations aren't area independent
    people *= grid_cell_area  # To adjust for incorrect grid size above

    mv_line_cost = 9000 # USD/km
    lv_line_cost = 5000 # USD/km
    discount_rate = 0.08 # percent
    mv_line_capacity = 50 # kW/line
    lv_line_capacity = 10 # kW/line
    lv_line_max_length = 30 # km
    hv_line_cost = 53000 # USD/km
    mv_line_max_length = 50 # km
    hv_lv_transformer_cost = 5000 # USD/unit
    mv_increase_rate = 0.1 # percentage

    consumption = people / NUM_PEOPLE_PER_HH * scenario
    average_load = consumption * (1 + distribution_losses) / HOURS_PER_YEAR
    peak_load = average_load / base_to_peak_load_ratio

    no_mv_lines = ceil(peak_load / mv_line_capacity)
    no_lv_lines = ceil(peak_load / lv_line_capacity)
    lv_networks_lim_capacity = no_lv_lines / no_mv_lines
    lv_networks_lim_length = ((grid_cell_area / no_mv_lines) / (lv_line_max_length / sqrt(2))) ** 2
    actual_lv_lines = ceil(min([people / NUM_PEOPLE_PER_HH, max([lv_networks_lim_capacity, lv_networks_lim_length])]))
    hh_per_lv_network = (people / NUM_PEOPLE_PER_HH) / (actual_lv_lines * no_mv_lines)
    lv_unit_length = sqrt(grid_cell_area / (people / NUM_PEOPLE_PER_HH)) * sqrt(2) / 2
    lv_lines_length_per_lv_network = 1.333 * hh_per_lv_network * lv_unit_length
    total_lv_lines_length = no_mv_lines * actual_lv_lines * lv_lines_length_per_lv_network
    line_reach = (grid_cell_area / no_mv_lines) / (2 * sqrt(grid_cell_area / no_lv_lines))
    total_length_of_lines = min([line_reach, mv_line_max_length]) * no_mv_lines
    additional_hv_lines = max(
        [0, round(sqrt(grid_cell_area) / (2 * min([line_reach, mv_line_max_length])) / 10, 3) - 1])
    hv_lines_total_length = (sqrt(grid_cell_area) / 2) * additional_hv_lines * sqrt(grid_cell_area)
    num_transformers = ceil(additional_hv_lines + no_mv_lines + (no_mv_lines * actual_lv_lines))
    generation_per_year = average_load * HOURS_PER_YEAR

    # The investment and O&M costs are different for grid and non-grid solutions
    if grid:
        td_investment_cost = hv_lines_total_length * hv_line_cost + \
                             total_length_of_lines * mv_line_cost + \
                             total_lv_lines_length * lv_line_cost + \
                             num_transformers * hv_lv_transformer_cost + \
                             (people / NUM_PEOPLE_PER_HH) * connection_cost_per_hh + \
                             additional_mv_line_length * (
                                 mv_line_cost * (1 + mv_increase_rate) ** ((additional_mv_line_length / 5) - 1))
        td_om_cost = td_investment_cost * om_of_td_lines
        total_investment_cost = td_investment_cost
        total_om_cost = td_om_cost

    else:
        total_lv_lines_length *= 0 if standalone else 0.75
        mv_total_line_cost = mv_line_cost * mv_line_length
        lv_total_line_cost = lv_line_cost * total_lv_lines_length
        installed_capacity = peak_load / capacity_factor
        capital_investment = installed_capacity * capital_cost
        td_investment_cost = mv_total_line_cost + lv_total_line_cost + (
                             people / NUM_PEOPLE_PER_HH) * connection_cost_per_hh
        td_om_cost = td_investment_cost * om_of_td_lines
        total_investment_cost = td_investment_cost + capital_investment
        total_om_cost = td_om_cost + (capital_cost * om_costs * installed_capacity)

    # The renewable solutions have no fuel cost
    if diesel:
        fuel_cost = diesel_price / efficiency
    elif grid:
        fuel_cost = grid_price
    else:
        fuel_cost = 0

    # Perform the time value LCOE calculation
    year = np.arange(0, system_life + 1)
    el_gen = generation_per_year * np.ones(system_life + 1)
    el_gen[0] = 0
    discount_factor = (1 + discount_rate) ** year
    it = np.zeros(system_life + 1) # investment
    it[0] = total_investment_cost
    mt = total_om_cost * np.ones(system_life + 1) # maintenance
    mt[0] = 0
    ft = el_gen * fuel_cost # fuel
    ft[0] = 0
    discounted_costs = (it + mt + ft) / discount_factor
    discounted_generation = el_gen / discount_factor

    return np.sum(discounted_costs) / np.sum(discounted_generation)

if __name__ == "__main__":
    print('Running as a script')
    scenario = input('Enter scenario value (int): ')
    specs_csv = input('Enter path to specs file: ')
    os.chdir('..')
    make_tables(scenario, specs_csv)
