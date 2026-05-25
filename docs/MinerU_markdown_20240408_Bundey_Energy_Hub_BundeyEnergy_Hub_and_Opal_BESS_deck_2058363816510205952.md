# Bundey Energy Hub Pty Ltd Bundey Energy Hub and Opal BESS analysis

8th April 2024 

Preliminary report 

![image](https://cdn-mineru.openxlab.org.cn/result/2026-05-14/72c3f3f8-bc83-40c3-9286-f83b8bcc13a3/9220bd964b364f86be3a22b721d143b6c394d498bf80d193403c6c76776fde66.jpg)


# Introduction

# Report objective:

Aurora Energy Research was commissioned by Bundey Energy Hub Pty Ltd to conduct a gross margin analysis of a standalone BESS, Bundey Energy Hub and Opal BESS 500 MW, South Australia. The technical parameters for these assets were supplied by Bundey Energy Hub Pty Ltd. Other asset-specific technical constraints, warranties or contracting strategies were not considered. 

# Market scenario:

The first section of the report presents the results of the asset specific DWA analysis. Specifically, Aurora has been asked to forecast the DWA price of the above assets in Aurora Central Q1 2024 scenario: 

▪ Aurora Central Q1 2024, which reflects the latest status-quo policy assumptions and Aurora’s central outlook on key inputs 

# Grid scenario:

Aurora MLF Central scenario was analysed using the Aurora Energy Research in-house dynamic network model AER-EN AUS: 

▪ Aurora MLF Central, buildout according to Aurora Central, including committed grid updates in the NEM 

# Report outputs:

This report shows outputs at a yearly granularity. The accompanying databook includes price outputs at yearly and monthly granularity. The FCAS forecast is provided at yearly granularity only. All prices in this report are shown in real $2022 values. All years in this report are in financial years, beginning 1st July and ending 30th June. 

# Wholesale modelling methodology:

Aurora’s NEM power market model forecasts wholesale prices based on the fundamentals of supply and demand in the market. As an equilibrium model, it does not produce the very high peaks in wholesale prices (>$1,000/MWh) that periodically arise in the NEM. To capture the impact of these very high price peaks, an additional step is added to the modelling process: 

▪ Firstly, Aurora’s AER-ES AUS model is run to produce a forecast of fundamental price volatility over the modelling horizon 

Secondly, AER-ES AUS is re-run and enabled to produce very high peak prices (+$1,000/MWh) using statistical methods and drawing on historical levels of peak price volatility. This produces a price forecast including peak price volatility. 

The analysis in this exercise uses the price forecasts including peak price volatility, with the results tranched to show battery revenues from the component of wholesale prices greater than >$300/MWh. 

# Agenda

I. Wholesale market modelling overview 

II. Asset-specific economics analysis 

III. MLF analysis 

IV. Appendix 

# Aurora Central scenario: summary of input assumptions as per Q1 2024

<table><tr><td colspan="2"></td><td>Aurora Central scenario assumptions</td></tr><tr><td rowspan="2">Policy</td><td>Federal emissions policy</td><td rowspan="2">Retention of the LRET in its current form until 2030No specific CO2 emissions target for the NEM; CO2 emissions for the NEM are an output of the modellingNSW: EIR1 partially met: 8.8GW renewable generation, and 0.6GW long-duration storage and 1075MW firming capacity by 2030QLD: Pre-2022 QRET2 assumed to be met. No requirement to meet updated QRET (70% by 2032, 80% by 2035)SA: No requirement to meet SRET3VIC: Pre-2022 VRET4 assumed to be met. VRET1 and VRET25 auction capacities included, 2GW offshore wind by 2034. No requirement to meet updated VRET (65% by 2030, 95% by 2035)TAS: No requirement to meet TRET6</td></tr><tr><td>State schemes</td></tr><tr><td rowspan="2">Demand</td><td>Underlying demand</td><td>Aurora in-house modelling</td></tr><tr><td>Rooftop solar, behind-the-meter batteries &amp; EVs</td><td>Aurora in-house modelling</td></tr><tr><td rowspan="2">Commodity prices</td><td>Gas prices</td><td>Aurora in-house global commodity price modelling - LNG netback prices</td></tr><tr><td>Coal prices</td><td>Aurora in-house global commodity price modelling - coal export price for uncontracted, non-mine-linked coal plants</td></tr><tr><td rowspan="3">Supply</td><td>Coal closures</td><td>AEMO&#x27;s latest (Feb. 2024) announced closure timeline with the exception of Callide B (closing at end of FY2026), Eraring (operates at half capacity post FY25 until closure in FY27), Millmerran and Callide C (both closing at end of FY2049), Stanwell (closing at end of FY2032), Kogan Creek (closing at end of FY2035), Tarong and Tarong North (both closing at end of FY2033), and Loy Yang B (closing at end of FY41. Closure dates may differ from AEMO due to modelled plant economics suggesting earlier retirement or new policy/announcements that are not yet reflected in AEMO&#x27;s timeline</td></tr><tr><td>Technology costs</td><td>Aurora in-house modelling</td></tr><tr><td>New Hydro</td><td>Kidston from 2025, Snowy 2.0 included from 2031, Borumba from 2032 and 0.6GW of NSW pumped hydro via the Electricity Infrastructure Roadmap</td></tr><tr><td rowspan="2">Network augmentation</td><td>Inter-regional</td><td>AEMO 2022 ISP Step Change Optimal Development Pathway unless otherwise stated: EnergyConnect, QNI &amp; VNI upgrades, QNI Connect and Marinus Link (only including first stage delayed to FY33)AEMO Draft 2024 ISP Step Change Optimal Development Pathway for: VNI-West</td></tr><tr><td>Intra-regional</td><td>AEMO 2022 ISP Step Change Optimal Development Pathway + Queensland Energy and Jobs Plan SuperGridAEMO Draft 2024 ISP Step Change Optimal Development Pathway for: Central-West Orana, New England and Western Renewables Link</td></tr><tr><td>Marginal Loss Factors</td><td>Endogeneity</td><td>Asset specific MLFs incorporated into short-run marginal costs and therefore bidding behaviourMLFs modelled endogenously by Renewable Energy Zone (REZ) ensuring that capacity buildout and DWA prices reflect the premium required in reality to bring on new investmentCurrent grid limits and robustness of MLFs factored into model build decisions</td></tr><tr><td>Bidding behaviour</td><td>Scarcity pricing / Uplift</td><td>Purpose-built uplift function - capturing the deltas between price and the short-run marginal cost of the system, based on historical behaviourIncorporates time-of-day/week, scarcity margin, technology, bidding behaviour etc.</td></tr></table>


1) Electricity Infrastructure Roadmap. Total program includes 12GW renewables, 2GW long duration storage by 2030 2) 50% of underlying demand met by renewable generation by 2030 3) 100% of underlying demand met by renewable generation by 2030 4) 40% and 50% renewable generation by 2025 and 2030 respectively 5) 600MW additional renewables by FY2025 6) 16TWh renewable generation by 2030, 21TWh renewable generation by 2040 



Source: Aurora Energy Research 


# Aurora’s coal closure schedule aligns with state-announced closures, while privately-owned assets are closed no later than their announced date

<table><tr><td>Coal Plants</td><td>State</td><td>Capacity MW</td><td>Aurora Central 24Q1 closure timeline1</td><td>AEMO&#x27;s expected closure timeline2</td><td>AEMO&#x27;s 2022 ISP Step Change closure timeline</td><td>AEMO&#x27;s Draft 2024 ISP Step Change closure timeline3</td></tr><tr><td>Bayswater</td><td>NSW</td><td>2740</td><td>2033</td><td>2034</td><td>2034</td><td>2032</td></tr><tr><td>Eraring4</td><td>NSW</td><td>2880</td><td>2028</td><td>2026</td><td>2026</td><td>2026</td></tr><tr><td>Liddell</td><td>NSW</td><td>1800</td><td>2024</td><td>2024</td><td>2024</td><td>2024</td></tr><tr><td>Vales Point B</td><td>NSW</td><td>1320</td><td>2034</td><td>2034</td><td>2027</td><td>2029</td></tr><tr><td>Mt Piper</td><td>NSW</td><td>1380</td><td>2041</td><td>2041</td><td>2040</td><td>2038</td></tr><tr><td>Callide B</td><td>QLD</td><td>700</td><td>2027</td><td>2029</td><td>2026</td><td>2028</td></tr><tr><td>Callide C</td><td>QLD</td><td>840</td><td>2050</td><td>-</td><td>2040</td><td>2034</td></tr><tr><td>Gladstone</td><td>QLD</td><td>1680</td><td>2036</td><td>2036</td><td>2031</td><td>2032</td></tr><tr><td>Kogan Creek</td><td>QLD</td><td>744</td><td><eq>2036^5</eq></td><td>2043</td><td>2029</td><td>2035</td></tr><tr><td>Millmerran</td><td>QLD</td><td>852</td><td>2050</td><td>2052</td><td>2043</td><td>2035</td></tr><tr><td>Stanwell</td><td>QLD</td><td>1460</td><td><eq>2033^5</eq></td><td>2047</td><td>2034</td><td>2033</td></tr><tr><td>Tarong</td><td>QLD</td><td>1400</td><td><eq>2034^5</eq></td><td>2038</td><td>2028</td><td>2034</td></tr><tr><td>Tarong North</td><td>QLD</td><td>450</td><td><eq>2034^5</eq></td><td>2038</td><td>2029</td><td>2034</td></tr><tr><td>Loy Yang A</td><td>VIC</td><td>2225</td><td>2036</td><td>2036</td><td>2033</td><td>2034</td></tr><tr><td>Loy Yang B</td><td>VIC</td><td>1140</td><td>2042</td><td>2048</td><td>2030</td><td>2032</td></tr><tr><td>Yallourn</td><td>VIC</td><td>1450</td><td>2029</td><td>2029</td><td>2027</td><td>2029</td></tr></table>


1) First financial year without generating capacity; 2) Timeline extracted from AEMO’s Generating unit expected closure year – July 2023 3) Refers to year when final unit id decommissioned 4) Based on finding from the 2023 ESOO report the NSW Government is negotiating with Origin to keep half of Eraring’s capacity running until FY27 to avoid potential system security and reliability shortfalls 5) Based on the QEJP timeline 



Sources: Aurora Energy Research, AEMO 


# The Draft 2024 ISP sees slower coal retirements through the 2020s than the 2022 ISP and 2024 Draft ISP, but all coal exits by FY2038


Coal capacity in NEM, and scheduled retirements in Aurora Central1


![image](https://cdn-mineru.openxlab.org.cn/result/2026-05-14/72c3f3f8-bc83-40c3-9286-f83b8bcc13a3/0a685818f11d5447a1823879e04f37353f694c02bc87063ef6cd17da54f2a657.jpg)



1) Line chart represents end-of-financial-year capacity


# Coal closures timeline:

Aurora Central sees a slower coal retirement schedule compared to AEMO’s Draft 2024 ISP Step Change. 

The more aggressive closure timeline under the Draft 2024 ISP is imposed to achieve Australia’s net zero 2050 commitment and help limit global temperature rise to 2°C. 

As seen with the closure of Hazelwood, large potential maintenance costs and/or safety upgrades towards a plant’s end of technical life pose a significant uncertainty for coal asset owners. 

These can often precipitate earlier or later closure depending on when in the asset’s lifecycle these events occur. 

Aurora Central only closes coal plants at the asset owner’s announced dates, or earlier if the economics prove unfavourable. It is important to stress that forecasting coal closure exits is challenging, particularly without access to private information from coal power station owners. 

# The coal price cap has been extended to June 2024; Aurora expects coal prices to climb once the cap ends due to robust demand for coal across Asia


Gas price forecast1



A$/GJ, real 2022


![image](https://cdn-mineru.openxlab.org.cn/result/2026-05-14/72c3f3f8-bc83-40c3-9286-f83b8bcc13a3/ded6ed6d32c21f65d82712722d0d07604a03bb2bdc09ca3f93e27d80008fb08f.jpg)


▪ Aurora’s domestic gas price forecast represents prices at Wallumbilla and is based on the netback price to Aurora’s JKM (Japanese LNG) price. 

▪ Australian prices briefly decoupled from netback prices (historical lines) following a strong recovery in LNG demand across Asia and Europe, and Aurora’s forecasts reflect the strong market but similarly decouple from netback prices in the short term. 

▪ In the short-term, the Federal Government’s cap of $12/GJ on new gas contracts affects prices for FY24-25. An extension of the gas price cap to July 2025 has been announced, when it will be subject to a further review. 

![image](https://cdn-mineru.openxlab.org.cn/result/2026-05-14/72c3f3f8-bc83-40c3-9286-f83b8bcc13a3/2f08c6f6b2016c9108c5c07b1a5fd7e8da0a1df299de662d1735a2e57f15df20.jpg)



Coal price forecast2



A$/GJ, real 2022


![image](https://cdn-mineru.openxlab.org.cn/result/2026-05-14/72c3f3f8-bc83-40c3-9286-f83b8bcc13a3/145a41be4294fab8c31afba4bd66bd750a9ff0ee86966b92f5aa9ce4d05ffa23.jpg)


▪ Aurora’s Newcastle coal price forecast is linked to our forecast for the global export value of coal. 

Plant specific coal prices are used in combination with the export price to best reflect contract positions and mine-linked behaviour. 

▪ The NSW Government’s decision to extend the $125/t coal cap to the 30 June 2024 has suppressed coal prices in the short term. 

▪ Higher coal prices are expected to emerge once the cap ends reflecting robust demand for coal across Asia. 

![image](https://cdn-mineru.openxlab.org.cn/result/2026-05-14/72c3f3f8-bc83-40c3-9286-f83b8bcc13a3/e43422f0bb9124ed640ad46de53673b106c017f85a174a96f4520f277be0f161.jpg)


# Aurora’s interconnector assumptions broadly align with AEMO’s 2022 ISP ODP whilst incorporating select network delays

![image](https://cdn-mineru.openxlab.org.cn/result/2026-05-14/72c3f3f8-bc83-40c3-9286-f83b8bcc13a3/90ccf8f3f091c96d0edf4d92df3931c7aa2576381ca4a635212049691335539e.jpg)


# Aurora’s interconnector assumptions:

Aurora Central’s assumptions around interconnector augmentations were based on AEMO’s 2022 ISP Optimal Development Pathway (ODP). 

Whilst Aurora is largely aligned with AEMO on the timings of interconnector augmentations Aurora diverges on - (i) Marinus Link Stage 1, incorporating a three-year delay to 2033; and (ii) VNI-West, based on latest timings indicated by the Draft 2024 ISP ODP. 

Aurora Central omits Stage 2 of MarinusLink due to uncertainty surrounding future funding of the project1. 

# Compared to Aurora Central, AEMO’s demand forecasts are increasingly bullish reflecting rapid rates of electrification to decarbonise the NEM


Underlying demand1


![image](https://cdn-mineru.openxlab.org.cn/result/2026-05-14/72c3f3f8-bc83-40c3-9286-f83b8bcc13a3/39f3846c3a91a93709e39c08a93e07052fe2af157b95b618808f05b44389e75b.jpg)



Operational demand2



Aurora Central 2020 ISP Central 2022 ISP Step Change Draft 2024 ISP Step Change History


# Comparison of demand forecasts:

AEMO has significantly revised its demand forecast upwards since the 2020 ISP and is now more bullish than Aurora’s forecast. 

AEMO’s Draft 2024 ISP Step Change scenario underlying demand forecast exceeds 400TWh by 2050 to achieve economy-wide net zero and carbon budgets. 

The Step Change scenario’s higher demand outlook is driven by greater electric vehicle uptake, hydrogen production and electrification of industry to achieve net-zero ambitions. 

Based on the fundamentals of GDP, population and energy efficiency outlook, Aurora’s in-house demand modelling forecasts growth in underlying demand, driven predominately from the commercial sector in early years and EVs in later years. 

□ Aurora’s near-term demand projection aligns with the 2022 Electricity Statement of Opportunities. 

# Aurora sees green value extend beyond 2030, but falling very quickly to $1/MWh from 2040 onwards


Forecast LGC/green certificate prices



A$/MWh, real 2022


![image](https://cdn-mineru.openxlab.org.cn/result/2026-05-14/72c3f3f8-bc83-40c3-9286-f83b8bcc13a3/47ecc6d10ef577abaf888bd6400daa72dc261f0ddf056f1197131c8b7ca4d9f4.jpg)


# Potential green certificate value beyond

In Aurora’s modelling, the LGC price inputs are based on current futures prices and trend down to $15/certificate in 2030. 

There is currently no legislated replacement for the Renewable Energy Target, but it is likely that a form of Guarantee of Origin (REGO) certificate will be designed and implemented by the mid-2020s. 

The 2023-2024 budget provided $38.2 million for the creation of a post 2030 renewable electricity certification scheme, it is clear there will be some form of REGO certificate post 2030. 

To reflect one plausible outcome based upon the REGO draft design, Aurora has incorporated a green certificate price of $10 in 2031, which declines linearly to reach $1 in 2040, after which it remains constant at $1 until 2060. 

Aurora will continue to monitor progress on legislating Renewable Energy Guarantee of Origin (REGO) certificates and will reflect such a policy in forecasts once additional details are confirmed. 

# In Aurora Central, the NEM is expected to become increasingly dominated by renewable and flexible technologies


NEM-wide capacity, Aurora Central, Q1 2024


![image](https://cdn-mineru.openxlab.org.cn/result/2026-05-14/72c3f3f8-bc83-40c3-9286-f83b8bcc13a3/23c1d44786510509d95b4f5e9cd46893a188bd28109b3f5b87944af1bc396ea3.jpg)



Total NEM dispatchable1 capacity, GW


# Aurora Central capacity expansion:

State backed renewable projects help drive renewable buildout in the late 2020s, with an increase in onshore wind capacity of 32% from FY25 to FY30. 

Growth in renewables continues in the 2030s and 40s as current grid constraints are relieved with transmission augmentation. 

Coal capacity retirements accelerate from the late 2020s as costs increase with end-of-life issues and greater required ramping. 

The buildout of grid-scale batteries accelerates in the 2030s as costs continue to fall and mid-merit gas exits, leaving spreads set more often between renewable and gas peaking plants. 

By 2050, wind and solar capacity dominate the market with over 109.4GW of capacity being forecast to be built. 

# In Aurora Central, SA is expected to become increasingly dominated by renewable and flexible technologies


SA capacity, Aurora Central, Q1 2024



Nameplate GW


![image](https://cdn-mineru.openxlab.org.cn/result/2026-05-14/72c3f3f8-bc83-40c3-9286-f83b8bcc13a3/2f475734978c41c79c44ea15d89e5bc08729c5ca0f1e1ae82530b4332d52902c.jpg)



Total NEM dispatchable1 capacity, GW


# Aurora Central capacity expansion:

State backed renewable projects help drive renewable buildout in the 2020s, with an increase in solar capacity of 59% from FY25 to FY30. 

Growth in renewables continues in the 2030s and 40s as current grid constraints are relieved with transmission augmentation. 

The buildout of grid-scale batteries accelerates in the 2030s as costs continue to fall and mid-merit gas exits, leaving spreads set more often between renewable and gas peaking plants. 

By 2050, wind and solar capacity dominate the market with over 10.7GW of capacity being forecast to be built. 

# SA TWA prices average $98/MWh in Aurora Central

South Australia TWA Prices1 

AUD$/MWh, real 2022 

![image](https://cdn-mineru.openxlab.org.cn/result/2026-05-14/72c3f3f8-bc83-40c3-9286-f83b8bcc13a3/98bdd50c5dd17ce24936ef19c9739e183f02d461d37e95a6014c7771b4269eb9.jpg)



1) Prices are from Aurora’s “spiky price” series, which accounts for a higher frequency of price volatility, calibrated historically.


Aurora Central sees South Australia TWA prices decline over the mid-2020s as renewables buildout continues. 

SA prices will fall slightly in 2027 when project EnergyConnect will be commissioned in 2027, connecting NSW and SA. 

The SA TWA price will experience a jump in 2029 due to the closure of Yallourn (1.5GW). 

The prices will decline slightly in the early 2030s as Snowy 2.0 commenced in 2031. 

South Australia TWA prices are expected to rise throughout the mid-2030s as existing coal assets retire, with a noticeably sharp rise in 2036 following the closure of Loy Yang A (2.3GW). 

# In valuing Bundey Energy Hub and Opal BESS, we also consider the potential revenue streams from the occasional peak price events (>$300/MWh)


South Australia frequency of >$300/MWh prices1



Number of half-hours in a year


![image](https://cdn-mineru.openxlab.org.cn/result/2026-05-14/72c3f3f8-bc83-40c3-9286-f83b8bcc13a3/96f279404c091719d226c874aa79d1b93ea16b29e5d490e91945f5cb30a7a173.jpg)



1) Count of all prices >$300/MWh. 2)While extreme price events have been evident in recent history, these events are often harder to predict. We would therefore recommend a higher discount rate for revenues made during periods where prices are >$300/MWh


# Projected peak prices across Aurora Central scenario

▪ South Australia has seen a number of high prices (>$300/MWh). 

These are often due to “out of equilibrium” outcomes such as transitory network constraints, unforeseen supply/demand imbalances, generator islanding, etc which are not captured in Aurora’s standard equilibrium model. 

To capture these additional value, a further step is added to the fundamentals modelling process, which calibrates peak price volatility based on statistical methods that draws on observed historic of (>$1000/MWh and <-$100/MWh) prices. 

As these events and prices are typically harder to predict, we provide these values as a separate “tranche” to clients, and would recommend a higher discount rate2. 

The occurrence of extreme high price events drops with the full commissioning of Project EnergyConnect. 

Upon the exit of Loy Yang A, we see a surge in frequency high events due to a significant reduction in baseload generation in Victoria. 

# Intraday 2-hour price spreads in Aurora Central average $240/MWh

Average South Australia intra-day 2-hour wholesale price spread1,2 

$A/MWh, real 2022 

![image](https://cdn-mineru.openxlab.org.cn/result/2026-05-14/72c3f3f8-bc83-40c3-9286-f83b8bcc13a3/0cf7f7faf3de7526b41d47a05c283d70d020c14272ae614b00ec5ee6afed98aa.jpg)



1) Daily average spread is defined as the daily max 2-hour minus min 2hour half-hourly price 2) Historical prices are nominal and in calendar year to allow a full year data; and forecast prices in real 2022.


# Intraday wholesale price spread in SA

South Australia intra-day price volatility is expected to average $240/MWh in the Central throughout the forecast horizon. 

South Australia experiences larger price spreads in the near-term as increased levels of rooftop solar lowers prices during the day, while more expensive flexible technology is required during morning and evening peaks to meet demand. 

The price spread drops in FY27 with the entry of Project EnergyConnect, connecting SA to NSW. This allows energy export from SA to NSW when SA has excessive renewable generation, and SA is firmed up by importing from nearby states when there is a short-fall of renewable generation. This results in intraday price spreads narrowing in the late-20s and stabilizing over the forecast 

# FCAS prices are forecast to decrease significantly over the medium term, primarily due to new batteries entering the market

FCAS prices by service1 

A$/MW/hr, real 2022 


Regulation Raise


![image](https://cdn-mineru.openxlab.org.cn/result/2026-05-14/72c3f3f8-bc83-40c3-9286-f83b8bcc13a3/869f743cb2c48206e93355beef63d3a9fdff1a19da6b93ba072fca4d28b9dcfe.jpg)



Contingency Raise 1 sec


![image](https://cdn-mineru.openxlab.org.cn/result/2026-05-14/72c3f3f8-bc83-40c3-9286-f83b8bcc13a3/575b97105dcb25284baee966a6aada63d6c14c4ad16e37240f540894fff15a44.jpg)



Contingency Raise 60 secs


![image](https://cdn-mineru.openxlab.org.cn/result/2026-05-14/72c3f3f8-bc83-40c3-9286-f83b8bcc13a3/7f04a7b374a73e5e68014097135e2a12a86416e0ea154cb2f3440f78f3bd5cd9.jpg)



Regulation Lower


![image](https://cdn-mineru.openxlab.org.cn/result/2026-05-14/72c3f3f8-bc83-40c3-9286-f83b8bcc13a3/af64591d5fc379f5c0d9c4b76e343185820e5858a6cc3a88c6840e88d4d6f9c2.jpg)



Contingency Raise 6 secs


![image](https://cdn-mineru.openxlab.org.cn/result/2026-05-14/72c3f3f8-bc83-40c3-9286-f83b8bcc13a3/a785daa8de64a2d5b4d3c6893d850387c209dfba779c5fefad3bf1c5f573aaf0.jpg)



Contingency Raise 5 min


![image](https://cdn-mineru.openxlab.org.cn/result/2026-05-14/72c3f3f8-bc83-40c3-9286-f83b8bcc13a3/dade2f779a6d0ceff2e7e946bc5d71332065a676fe65930ac9500752e76b840e.jpg)


# FCAS markets have expanded significantly in recent years; they are forecast to decline in line with FCAS prices


FCAS expenditure by service: history1 vs. Central



Million A$


![image](https://cdn-mineru.openxlab.org.cn/result/2026-05-14/72c3f3f8-bc83-40c3-9286-f83b8bcc13a3/f91208e7789fde290e74ee41d8e016cdc923f4d8ca72f1cb4ef945d195611731.jpg)



1) Global and local FCAS costs from AER. Historical values are nominal while forecast values are real 2022.


# Forecast of FCAS expenditure

Between FY2015 and 2022, FCAS expenditure increased by $355 million, a more than ten-fold increase over seven years. 

2020 saw unprecedented FCAS costs, driven by islanding events, with a similar total cost observed in 2022. 

Looking forward, the size of FCAS markets is forecast to decline in line with falling FCAS prices. 

The effect of lower prices is partially offset by forecast increased requirement for regulation services as the share of variable renewables increases. 

Our forecasts do not include FCAS local costs, as these are not forecasted as part of Aurora’s modelling exercise (see next slide). 

# Islanding events have contributed significantly to total FCAS “local” costs; Aurora’s forecasts do not include these “local” components


FCAS expenditure: historical global vs local1, Central forecast2



Million A$


![image](https://cdn-mineru.openxlab.org.cn/result/2026-05-14/72c3f3f8-bc83-40c3-9286-f83b8bcc13a3/3bba9ce2d148249a84e0f9c0113434ebd3cd8addf2b408e55ca2e69210654d2c.jpg)



FCAS local expenditure by state



Million A$


![image](https://cdn-mineru.openxlab.org.cn/result/2026-05-14/72c3f3f8-bc83-40c3-9286-f83b8bcc13a3/00bcf9b97a0c587f47ffba37800d1b6fcae7e3e14bf07cc7e9cc06f2ec7d7a90.jpg)


![image](https://cdn-mineru.openxlab.org.cn/result/2026-05-14/72c3f3f8-bc83-40c3-9286-f83b8bcc13a3/3e7882309f1b5f6ccee9ee99e4bbd8d51fb877f3a552ac99576b1bf559bd1f95.jpg)


Local costs 

![image](https://cdn-mineru.openxlab.org.cn/result/2026-05-14/72c3f3f8-bc83-40c3-9286-f83b8bcc13a3/1f393af9da4e83a331f0f640e2acd4b8b01cfbe249e77dc0bd946f4780be6f74.jpg)


Global 

![image](https://cdn-mineru.openxlab.org.cn/result/2026-05-14/72c3f3f8-bc83-40c3-9286-f83b8bcc13a3/c76886ff83e58c40ebe47bc0ffc09c3637cbcd8928c4e5ae089198732b43dd75.jpg)


TAS 

![image](https://cdn-mineru.openxlab.org.cn/result/2026-05-14/72c3f3f8-bc83-40c3-9286-f83b8bcc13a3/721d1366649616331bad867df517b369576bf6778ddaf5d4816080241fc35bca.jpg)


![image](https://cdn-mineru.openxlab.org.cn/result/2026-05-14/72c3f3f8-bc83-40c3-9286-f83b8bcc13a3/8605285861e9cbef67096fa884f5a325398d61f2e755f0160889477db717345a.jpg)


SA 

# Comparison of historical FCAS

# expenditure “local” vs “global”

▪ Aurora’s forecast considers NEM-wide FCAS procurement i.e. “globally”. 

However, under various system conditions including islanding of regions, “local” FCAS is procured within a region. 

Local provision of FCAS tends to result in higher prices and costs given the smaller pool of providers. 

Islanding has occurred in SA and QLD, while TAS is always islanded from the mainland due to its DC-only connection. 

Aurora’s forecasts do not include islanding events or similar system security events that historically have led to FCAS prices spikes. 

# Agenda

Wholesale market modelling 

II. Asset-specific economics analysis 

1. Methodology 

2. Bundey Energy Hub and Opal BESS 

III. MLF analysis 

IV. Appendix 

# There are a variety of factors that create a long-term premium over the LCOE for renewable technologies

![image](https://cdn-mineru.openxlab.org.cn/result/2026-05-14/72c3f3f8-bc83-40c3-9286-f83b8bcc13a3/2e605a502a0035efa34c0381a8d1f6b33b614af89205f1f8b4e12b4868e339fd.jpg)


# Agenda

Wholesale market modelling 

II. Asset-specific economics analysis 

1. Methodology 

2. Bundey Energy Hub and Opal BESS 

III. MLF analysis 

IV. Appendix 

# The following asset-specific characteristics were used to model the Bundey Energy Hub and Opal BESS

<table><tr><td>Asset specifications</td><td>Bundey Energy Hub and Opal BESS</td></tr><tr><td>Commission date</td><td>January, 2026</td></tr><tr><td>Location</td><td>Bundey, SA</td></tr><tr><td>Charge and discharge size</td><td>500 MW charge, 500 MW discharge</td></tr><tr><td>Duration</td><td>2 hr</td></tr><tr><td>Battery initial storage</td><td>1000 MWh</td></tr><tr><td>Asset availability</td><td>99%</td></tr><tr><td>Lifetime (max)</td><td>25 years</td></tr><tr><td>Round Trip Efficiency (RTE)</td><td>85%</td></tr><tr><td>MLFs (generation/load)</td><td>1/1</td></tr><tr><td>Percentage of capacity available for Contingency FCAS</td><td>57%</td></tr><tr><td>Capacity available for Regulation FCAS</td><td>Up to 80MW</td></tr><tr><td>Degradation Profile</td><td>Provided by Bundey Energy Hub Pty Ltd</td></tr><tr><td>Cycling constraints</td><td>365 cycles per year</td></tr></table>

# In Aurora Central, the annual gross margin of the project BESS averages $64m over the forecasts, with peaks reaching ~$73m in 2036

Annual gross margins1 

$million, real 2022 


1 Aurora Central


![image](https://cdn-mineru.openxlab.org.cn/result/2026-05-14/72c3f3f8-bc83-40c3-9286-f83b8bcc13a3/4097de7489e5fa6030e7def9851110eb93f5bfe0dfbe03c493dd738db6abeb79.jpg)



1) Results presented on a financial year basis


# Bundey Energy Hub and Opal BESS gross margins projections – Aurora Central

In Aurora Central, Bundey Energy Hub and Opal BESS is forecasted to have an annual average gross margin of ~$64m throughout its lifetime. 

Gross margin hits $73m in 2036 coinciding with closure of Loy Yang A. 

High price events towards the end of the forecast are correlated with phasing out of the baseload generation across the NEM and higher renewable penetration. 

The proportion of gross margin from peak pricing (> $300/MWh) shows an upward trajectory, while revenue from energy arbitrage (transactions below $300/MWh) stabilises over time. 

Considering the BESS capacity of 500MW, Aurora Central anticipates that energy arbitrage will serve as the primary revenue streams throughout the asset’s lifespan, while regulation and contingency FCAS payments are considered a reliable secondary source of operating income. 

# Agenda

Wholesale market modelling 

II. Asset-specific economics analysis 

III. MLF analysis 

1. MLF inputs 

2. MLF results 

IV. Appendix 

# Asset-specific grid details provided for the network study

<table><tr><td></td><td>Bundey Energy Hub and Opal BESS</td></tr><tr><td>Asset size (MW-AC)</td><td>500 MW AC</td></tr><tr><td>Asset location</td><td>Bundey, SA</td></tr><tr><td>Expected Commissioning Date</td><td>Jan 1<eq>^{st}</eq> 2026</td></tr><tr><td>Modelling Commissioning Date</td><td>Jan 1<eq>^{st}</eq> 2026</td></tr><tr><td>Transmission connection location</td><td>Bundey Substation</td></tr><tr><td>Transmission line voltage (kV)</td><td>275</td></tr><tr><td>Transmission Node Identifier</td><td>Bundey Substation</td></tr></table>


Illustration of asset transmission connection location


![image](https://cdn-mineru.openxlab.org.cn/result/2026-05-14/72c3f3f8-bc83-40c3-9286-f83b8bcc13a3/99e4b9e50a7257f6e134acb479c64f56f5a2bf0f583dd8506d6c9089d288c6d1.jpg)


# Interconnector and grid upgrades through South Australia improve the robustness of the grid and support energy flows to major load centers

<table><tr><td></td><td>Project Name</td><td>Assumed commissioning date</td></tr><tr><td>1</td><td>Project Energy Connect</td><td>2025</td></tr><tr><td>2</td><td>South East South Australia REZ expansion - Stage 1</td><td>2029</td></tr><tr><td>3</td><td>Mid North Group Constraint – Option 1 or 2</td><td>2042</td></tr><tr><td>4</td><td>Leigh Creek – Option 1 or 2</td><td>2043</td></tr><tr><td>5</td><td>South East South Australia REZ expansion - Stage 2</td><td>2049</td></tr><tr><td>6</td><td>Riverland – Option 1</td><td>2050</td></tr></table>


South Australia Aurora Central network augmentations


![image](https://cdn-mineru.openxlab.org.cn/result/2026-05-14/72c3f3f8-bc83-40c3-9286-f83b8bcc13a3/4256e55c539b0135bd78c6058cce62f2d256040f3fbce39bcdef795359ae3d1b.jpg)


# Aurora has conducted MLF analysis on the Bundey Energy Hub and Opal BESS based off Aurora Central

<table><tr><td></td><td>MLF Central</td></tr><tr><td>Short-term renewable build-out</td><td>Existing and committed assets1</td></tr><tr><td>Medium / long term renewable build-out</td><td>Build-out according to Aurora Central</td></tr><tr><td>Grid augmentation outlook</td><td>AEMO 2022 ISP Step Change, with market announcements via Queensland Energy &amp; Jobs Plan, and updated project assumptions in the 2024 Draft ISP2</td></tr></table>

# Aurora has implemented delays to key network projects based on AEMO’s Draft 2024 ISP

# AEMO’s Draft 2024 ISP indicates delays to some upcoming network projects

▪ Findings from AEMO’s newly released Draft 2024 ISP are broadly aligned with the 2022 ISP, with previously identified network projects still assessed to deliver net market benefits for consumers. 

▪ Key differences between ISP releases include: 

▪ Progression in development stage for certain network projects 

▪ Updated timings based on feedback from project proponents 

Transmission costs rising by 30% on average reflecting supply chain issues, labour shortages, higher capex and financing costs, etc.1 

▪ The 2024 Q1 Aurora Central release incorporates delays to select network projects, listed in the table below, based on their importance to renewable generation investment in the short-term. 


Incorporated changes to key network projects


<table><tr><td rowspan="2" colspan="2">Transmission project</td><td colspan="4">Commissioning year (financial year)</td></tr><tr><td>Final 2022 ISP</td><td>Draft 2024 ISP</td><td>2023 Q4 Aurora</td><td>2024 Q1 Aurora</td></tr><tr><td>1</td><td>Central-West Orana REZ Transmission Link</td><td>2026</td><td>2028</td><td>2026</td><td>2028</td></tr><tr><td>2</td><td>Western Renewables Link</td><td>2027</td><td>2028</td><td>2027</td><td>2028</td></tr><tr><td>3</td><td>New England REZ Transmission Link</td><td>2028</td><td>2029</td><td>2028</td><td>2029</td></tr><tr><td>4</td><td>VNI West</td><td>2032</td><td>2030</td><td>2029</td><td>2030</td></tr></table>


Future state of the network


![image](https://cdn-mineru.openxlab.org.cn/result/2026-05-14/72c3f3f8-bc83-40c3-9286-f83b8bcc13a3/7d8519156554276bcc617107f94fa3f2a28d55dd88f244972feae05eecb633aa.jpg)


# Agenda

Wholesale market modelling 

II. Asset-specific economics analysis 

III. MLF analysis 

1. MLF inputs 

2. MLF results 

IV. Appendix 

# Historic MLFs of comparable, existing assets nearby the BEHO BESS


Historic MLFs around Bundey Energy Hub and Opal BESS


![image](https://cdn-mineru.openxlab.org.cn/result/2026-05-14/72c3f3f8-bc83-40c3-9286-f83b8bcc13a3/f31bbc079431ae99e60f0b1bc38c1f6ce0286fb04be02883143d24452c611f52.jpg)



CONNECTION VOLTAGE


![image](https://cdn-mineru.openxlab.org.cn/result/2026-05-14/72c3f3f8-bc83-40c3-9286-f83b8bcc13a3/0291b8ab618692cd411d8c9b0981cfd4c1d8c8e81a70192a85f3bc6b412cbd83.jpg)



South Australia Transmission Infrastructure


![image](https://cdn-mineru.openxlab.org.cn/result/2026-05-14/72c3f3f8-bc83-40c3-9286-f83b8bcc13a3/7b4f30f8fc1e66da50d5df19625fb80b864cbbeed85833a1d610e4e747b32c4b.jpg)


▪ The Bundey Energy Hub and Opal BESS’s 2026 MLFs is expected to be similar to existing renewable assets in South Australia, with generation MLF at around 0.95, and load MLF at 0.98. 

▪ The historical MLFs in the nearby sub-region decreased in the past years, primarily driven by increased imports to South Australia via Murraylink and additional generation capacity within this sub-region. 

# BEHO BESS generation MLFs are robust over the forecast, while its load MLFs are expected tobenefit from RE expansion and increased export to NSW


Generation MLFs for Bundey Energy Hub and Opal BESS


![image](https://cdn-mineru.openxlab.org.cn/result/2026-05-14/72c3f3f8-bc83-40c3-9286-f83b8bcc13a3/546664156561a29300231c5bbe229f493dfd59f688d13085c5b22631c4921fcc.jpg)



SA-NSW interconnector flows: SA’s exports to and imports from NSW


![image](https://cdn-mineru.openxlab.org.cn/result/2026-05-14/72c3f3f8-bc83-40c3-9286-f83b8bcc13a3/1205f7580ca58e53519376e7f107a85296719291ed67bdd808d1b8ed13f1a7b6.jpg)



Central scenario SA network augmentations


![image](https://cdn-mineru.openxlab.org.cn/result/2026-05-14/72c3f3f8-bc83-40c3-9286-f83b8bcc13a3/7f34295b8659ce1f8cf47a5ce575c15febd5cfeace4a791bb9153693d9f75ca8.jpg)


▪ The BEHO BESS Central MLF forecast resides approximately in the 0.95-0.96 range for generation and 0.93-0.99 for load . 

The forecast anticipates a favourable downward trend for BEHO BESS load MLFs due to its proximity to the soon-to-be-commissioned Project EnergyConnect. Consequently, its load MLFs are expected to decrease as net exports increase over the forecast period. 

▪ BEHO BESS generation MLFs are expected to remain robust throughout the forecast period, with key grid augmentations supporting its generation flow to major load centres. 

▪ Major movements in the MLF Central include: 

o 2027: Project EnergyConnect provide an interconnection between SA and NSW 

o 2029: Commission of SE South Australia REZ expansion and closure of Yallourn coal plant in Vic; 

o 2035: Loy Yang A exits, thereby significantly shifting the VIC/NSW/SA trade balance with reducing VIC exports to other states. 

# Agenda

Wholesale market modelling overview 

II. Asset-specific economics analysis 

III. MLF analysis 

IV. Appendix 

1. Model input assumptions 

2. Modelling approach – Market, Grid and Battery 

3. System Incident and Island Events 

4. Glossary 

# The NEM is an energy-only market that covers the east of Australia

# National Electricity Market (NEM) Overview

▪ The Australian National Electricity Market (NEM) is an energy-only market operated centrally for the states of New South Wales, Queensland, South Australia, Tasmania, and Victoria. 

Other parts of the country, most notably Western Australia and the Northern Territory, are not connected to the NEM. 

▪ The NEM is operated by AEMO, and is a gross pool market with mandatory participation. 

Registered generators sell all of their electricity through the market in a centrally coordinated process (this means that the merit order for demand in a particular location would include all available sources of supply in the NEM, with corresponding price premiums added for loss factors via transmission). 

▪ The market is physically dispatched and settled in five-minute windows. 

▪ As an energy-only market, the market price cap is set at $16,600/MWh2 such that price spikes provide a sufficient signal to incentivise new capacity. 

▪ Negative spot prices are also possible, with a price floor of -$1,000/MWh. 

While most decisions related to the NEM are made centrally, state governments still retain considerable authority over the subsequent execution. For instance, the degree of renewables support or measures to ensure security of supply. 


Renewable Zone map of the NEM1


![image](https://cdn-mineru.openxlab.org.cn/result/2026-05-14/72c3f3f8-bc83-40c3-9286-f83b8bcc13a3/785581a391777c7cbdc031502567c9c13e21c30fb2b48b12f858bede95575f8f.jpg)


# Overview of individual demand components

![image](https://cdn-mineru.openxlab.org.cn/result/2026-05-14/72c3f3f8-bc83-40c3-9286-f83b8bcc13a3/8085031e3fcb262e13c3833ccc1ce262cf2db43392eb1046e2b97d04ae2b8e32.jpg)


# Compared to Aurora Central, AEMO’s demand forecasts are increasingly bullish reflecting rapid rates of electrification to decarbonise the NEM


Underlying demand1


![image](https://cdn-mineru.openxlab.org.cn/result/2026-05-14/72c3f3f8-bc83-40c3-9286-f83b8bcc13a3/08ad612e6576d67a48acf16c53fb2c6a8c9694c9c112e108e66a20b4e3d1fadc.jpg)



Operational demand2



Aurora Central 2020 ISP Central 2022 ISP Step Change Draft 2024 ISP Step Change History


# Comparison of demand forecasts:

AEMO has significantly revised its demand forecast upwards since the 2020 ISP and is now more bullish than Aurora’s forecast. 

AEMO’s Draft 2024 ISP Step Change scenario underlying demand forecast exceeds 400TWh by 2050 to achieve economy-wide net zero and carbon budgets. 

The Step Change scenario’s higher demand outlook is driven by greater electric vehicle uptake, hydrogen production and electrification of industry to achieve net-zero ambitions. 

Based on the fundamentals of GDP, population and energy efficiency outlook, Aurora’s in-house demand modelling forecasts growth in underlying demand, driven predominately from the commercial sector in early years and EVs in later years. 

□ Aurora’s near-term demand projection aligns with the 2022 Electricity Statement of Opportunities. 

# Aurora’s distributed energy resource forecasts sit between the significantly revised 2020 and Draft 2024 ISP central projections


Rooftop solar



Nameplate GW


![image](https://cdn-mineru.openxlab.org.cn/result/2026-05-14/72c3f3f8-bc83-40c3-9286-f83b8bcc13a3/f0e5c4706085465155a018792a6a73fe6e0536d9563d7e2a0940842dfa645498.jpg)


AEMO’s Draft 2024 ISP shows even higher rooftop solar uptake compared to the 2022 ISP which was already bullish in comparison to Aurora Central’s outlook. 

▪ Aurora anticipates that the uptake of rooftop solar will be constrained by a range of factors: diminishing value in middle of the day power; costs to augment distribution networks; shifts in subsidy support to household or community batteries. 

▪ In the long-term, Aurora expects rooftop solar to reach 35GW as uptake numbers saturate towards 2050. 


Behind-the-meter batteries


![image](https://cdn-mineru.openxlab.org.cn/result/2026-05-14/72c3f3f8-bc83-40c3-9286-f83b8bcc13a3/fc035c8e85dcaf05cbd9aaf44793a8d7b73f13a6f7a450fa289f28cde8715d8a.jpg)


▪ AEMO’s Draft 2024 ISP, although lower than the 2022 ISP, is more optimistic in BTM battery installation compared to Aurora Central. 

AEMO’s BTM battery forecasts changed significantly between ISP publications, shifting from being more bearish in the 2020 ISP to forecasting 3.5x the level of build out by 2050 in the Draft 2024 ISP compared to Aurora Central. 


Electric vehicles1



Energy required, TWh


![image](https://cdn-mineru.openxlab.org.cn/result/2026-05-14/72c3f3f8-bc83-40c3-9286-f83b8bcc13a3/8f318277612705cfb507ff603c90d303510b3196283e6fd8fef57e13228afcef.jpg)


▪ Aurora Central’s EV growth is slower than AEMO’s Draft 2024 ISP over the forecast. Nonetheless, Aurora still expects 8.8 million EVs by 2040. 

Aurora Central sees 31TWh less demand from EVs than the Draft 2024 ISP Step Change scenario by 2050, where it previously saw 20TWh more EV demand than the 2020 ISP Central scenario. 

Aurora Central ISP 2020 Central 2022 Step Change Draft 2024 ISP Step Change 

# Utility-scale solar PV and Wind capex forecast and cost breakdown


Solar capex outlook1



A$/kW, real 2022


![image](https://cdn-mineru.openxlab.org.cn/result/2026-05-14/72c3f3f8-bc83-40c3-9286-f83b8bcc13a3/2a1e73eba18115cf38175487d0c49e6ca7d9bc421ed78ede696222c19a9cde8d.jpg)



Solar capex breakdown - 2023



A$/kW, real 2022


![image](https://cdn-mineru.openxlab.org.cn/result/2026-05-14/72c3f3f8-bc83-40c3-9286-f83b8bcc13a3/a216e322363506c1f3c472a1d46ec19087895ca6b195f4ff0e2c0de9650ab4a7.jpg)



Wind capex outlook1



A$/kW, real 2022


![image](https://cdn-mineru.openxlab.org.cn/result/2026-05-14/72c3f3f8-bc83-40c3-9286-f83b8bcc13a3/5becc074eac2b160086030f5cf867d4636ed6ad5922a71006ff2155483af80e3.jpg)



Wind capex breakdown - 2023



A$/kW, real 2022


![image](https://cdn-mineru.openxlab.org.cn/result/2026-05-14/72c3f3f8-bc83-40c3-9286-f83b8bcc13a3/8c8ca4ba1d9aa0cbd80d80324cbda9573d239a1ed6f3ed84e5a7e724acd7059c.jpg)



1) CAPEX excludes connection costs


Solar and wind capex forecast have been buoyed in the short term by supply chain issues. Longer term trends are driven by: 

# Solar

Future cost reductions are expected to be achieved through the increase in module efficiency, which is likely to reach 30% by 2050 

▪ This impacts CAPEX and OPEX through: 

− Less land area required 

Fewer modules to install 

− Less weight to transport 

# Wind

▪ Cost reductions are achieved from: 

CAPEX: improved rotor design, standardisation and reduced project contingencies 

Fixed OPEX: improvements from holistic approach to asset management and improved component manufacturing 

# BESS capex forecast and cost breakdown


1h BESS capex outlook1



A$/kW, real 2022


![image](https://cdn-mineru.openxlab.org.cn/result/2026-05-14/72c3f3f8-bc83-40c3-9286-f83b8bcc13a3/a741067b5704b8f81fd89c8274f1481359f9fb2baa24b2aee8db538f6a104322.jpg)



4h BESS capex outlook1


![image](https://cdn-mineru.openxlab.org.cn/result/2026-05-14/72c3f3f8-bc83-40c3-9286-f83b8bcc13a3/735a35878283a69a26645b41922fa29568caf14688805307c039109f5943a944.jpg)



2h BESS capex outlook1



A$/kW, real 2022


![image](https://cdn-mineru.openxlab.org.cn/result/2026-05-14/72c3f3f8-bc83-40c3-9286-f83b8bcc13a3/88a312793f54314c5b55416398ea2be9a393b967fe6e4042e34f5550039706a8.jpg)



BESS capex breakdown - 2023


![image](https://cdn-mineru.openxlab.org.cn/result/2026-05-14/72c3f3f8-bc83-40c3-9286-f83b8bcc13a3/32c80b31672d600dda44be0e98036774a2c9956f3a0524bcfb06a596eea81d55.jpg)


# Battery storage capex forecast

Aurora’s battery cost assumptions are based on our internal global database of the various components in addition to regular market sounding surveys with battery manufacturers. 

Battery costs are forecast to fall as the supply chains improve and technology learning rates reduce manufacturing costs. 

# Near-term solar projects included in Aurora Central


NEM solar projects


![image](https://cdn-mineru.openxlab.org.cn/result/2026-05-14/72c3f3f8-bc83-40c3-9286-f83b8bcc13a3/4947859f6fcea83b3f8a849c8e7d5aceb124a2783a26dba3174cd6f9c0a4e217.jpg)


<table><tr><td></td><td>Project Name</td><td>State</td><td>Capacity [MW]1</td><td>Expected Commissioning Date2</td><td>Status3</td></tr><tr><td>1</td><td>Quorn Park Solar Farm</td><td>NSW</td><td>80</td><td>2024</td><td>Anticipated</td></tr><tr><td>2</td><td>Wollar Solar Farm</td><td>NSW</td><td>280</td><td>2024</td><td>Committed</td></tr><tr><td>3</td><td>Yanco Solar Farm</td><td>NSW</td><td>60</td><td>2024</td><td>Anticipated</td></tr><tr><td>4</td><td>Walla Walla Solar Farm</td><td>NSW</td><td>300</td><td>2024</td><td>Committed</td></tr><tr><td>5</td><td>Wellington North Solar Farm</td><td>NSW</td><td>330</td><td>2025</td><td>Committed</td></tr><tr><td>6</td><td>Stubbo Solar Farm</td><td>NSW</td><td>400</td><td>2025</td><td>LTESA1 recipient</td></tr><tr><td>7</td><td>Culcairn Solar Farm</td><td>NSW</td><td>350</td><td>2027</td><td>LTESA3 recipient</td></tr><tr><td>8</td><td>Edenvale Solar Park</td><td>QLD</td><td>146</td><td>2024</td><td>In Commissioning</td></tr><tr><td>9</td><td>Wunghnu Solar Farm</td><td>VIC</td><td>75</td><td>2024</td><td>Committed</td></tr><tr><td>10</td><td>Derby Solar Farm</td><td>VIC</td><td>95</td><td>2025</td><td>VRET2 recipient</td></tr><tr><td>11</td><td>Horsham Solar Farm</td><td>VIC</td><td>119</td><td>2025</td><td>VRET2 recipient</td></tr><tr><td>12</td><td>Frasers Solar Farm</td><td>VIC</td><td>77</td><td>2025</td><td>Anticipated</td></tr><tr><td>13</td><td>Fulham Solar Farm</td><td>VIC</td><td>80</td><td>2025</td><td>VRET2 recipient</td></tr><tr><td>14</td><td>Kiamal Stage 2 Solar farm</td><td>VIC</td><td>150</td><td>2025</td><td>VRET2 recipient</td></tr><tr><td>15</td><td>Glenrowan Solar Farm</td><td>VIC</td><td>102</td><td>2025</td><td>Construction</td></tr></table>

# Future wind projects included in Aurora Central


NEM wind projects


![image](https://cdn-mineru.openxlab.org.cn/result/2026-05-14/72c3f3f8-bc83-40c3-9286-f83b8bcc13a3/83621e134a126ce6d3240f04e6b2b1088784b9c46663845a45775a712fb7838a.jpg)


<table><tr><td></td><td>Project Name</td><td>State</td><td>Capacity [MW]1</td><td>Expected Commissioning Date</td><td>Status2</td></tr><tr><td>1</td><td>Crookwell 3 Wind Farm</td><td>NSW</td><td>58</td><td>2024</td><td>PPA Agreed</td></tr><tr><td>2</td><td>Rye Park Wind Farm</td><td>NSW</td><td>396</td><td>2024</td><td>Committed</td></tr><tr><td>3</td><td>Flyers Creek Wind Farm</td><td>NSW</td><td>145</td><td>2024</td><td>Anticipated</td></tr><tr><td>4</td><td>Coppabella Wind Farm</td><td>NSW</td><td>275</td><td>2026</td><td>LTESA1 recipient</td></tr><tr><td>5</td><td>Uungula Wind Farm</td><td>NSW</td><td>400</td><td>2026</td><td>LTESA3 recipient</td></tr><tr><td>6</td><td>Dulacca Wind Farm</td><td>QLD</td><td>173</td><td>2024</td><td>In Commissioning</td></tr><tr><td>7</td><td>Kennedy Energy Park Wind Farm</td><td>QLD</td><td>43</td><td>2024</td><td>In Commissioning</td></tr><tr><td>8</td><td>Clarke Creek Wind Farm</td><td>QLD</td><td>450</td><td>2025</td><td>Committed</td></tr><tr><td>9</td><td>Forest Wind Farm</td><td>QLD</td><td>600</td><td>2026</td><td>SLA</td></tr><tr><td>10</td><td>MacIntyre Wind Farm</td><td>QLD</td><td>923</td><td>2025</td><td>Anticipated</td></tr><tr><td>11</td><td>Wambo Wind Farm</td><td>QLD</td><td>500</td><td>2025</td><td>State Funding3</td></tr><tr><td>12</td><td>Goyder South Wind Farm - Stage 1</td><td>SA</td><td>412</td><td>2024</td><td>Construction</td></tr><tr><td>13</td><td>Hawkesdale Wind Farm</td><td>VIC</td><td>97</td><td>2024</td><td>Committed</td></tr><tr><td>14</td><td>Ryan Corner Wind Farm</td><td>VIC</td><td>235</td><td>2024</td><td>Committed</td></tr><tr><td>15</td><td>Golden Plains Wind Farm- East</td><td>VIC</td><td>756</td><td>2026</td><td>Committed</td></tr></table>

Future battery projects included in Aurora Central 

<table><tr><td colspan="2">Project Name</td><td>Region</td><td>Nameplate Capacity [MW/MWh]</td><td>Expected Commissioning Date</td><td>Status</td></tr><tr><td colspan="6">Batteries included in the Central scenario</td></tr><tr><td>1</td><td>Broken Hill</td><td>NSW</td><td>50/50</td><td>2024</td><td>Construction</td></tr><tr><td>2</td><td>Sapphire Battery facility</td><td>NSW</td><td>30/38</td><td>2025</td><td><eq>Received\ EEP\ funding^{1}</eq></td></tr><tr><td>3</td><td>Waratah Super Battery</td><td>NSW</td><td><eq>850/1680^3</eq></td><td>2025</td><td>Construction</td></tr><tr><td>4</td><td>Orana BESS</td><td>NSW</td><td>408.5/1600</td><td>2025</td><td>LTESA2 recipient</td></tr><tr><td>5</td><td>Limondale Battery</td><td>NSW</td><td>50/400</td><td>2026</td><td>LTESA1 recipient</td></tr><tr><td>6</td><td>Smithfield BESS</td><td>NSW</td><td>65/130</td><td>2026</td><td>LTESA2 recipient</td></tr><tr><td>7</td><td>New England Battery</td><td>NSW</td><td>200/200</td><td>2027</td><td><eq>Construction^{1}</eq></td></tr><tr><td>8</td><td>Liddell Battery</td><td>NSW</td><td>500/1000</td><td>2027</td><td>LTESA2 <eq>recipient^{2}</eq></td></tr><tr><td>9</td><td>Silver City Energy Storage Project</td><td>NSW</td><td>200/1600</td><td>2028</td><td>LTESA3 <eq>recipient^{2}</eq></td></tr><tr><td>10</td><td>Goulburn River BESS</td><td>NSW</td><td>49/392</td><td>2028</td><td>LTESA3 recipient</td></tr><tr><td>11</td><td>Richmond Valley BESS</td><td>NSW</td><td>275/2200</td><td>2028</td><td>LTESA3 recipient</td></tr><tr><td>12</td><td>Representative batteries</td><td>NSW</td><td>351/1077</td><td>2025-2030</td><td>-</td></tr><tr><td>13</td><td>Chinchilla</td><td>QLD</td><td>100/200</td><td>2024</td><td>Construction</td></tr><tr><td>14</td><td>Greenbank BESS</td><td>QLD</td><td>200/400</td><td>2025</td><td>Publicly Announced</td></tr><tr><td>15</td><td>Hopeland BESS</td><td>QLD</td><td>175/350</td><td>2026</td><td>ARENA Funding</td></tr><tr><td>16</td><td>Mount Fox BESS</td><td>QLD</td><td>300/600</td><td>2026</td><td>ARENA Funding</td></tr><tr><td>17</td><td>Torrens Island</td><td>SA</td><td>250/250</td><td>2024</td><td>Construction</td></tr><tr><td>18</td><td>Tailem Bend BESS</td><td>SA</td><td>41.5/84</td><td>2024</td><td>In Commissioning</td></tr><tr><td>19</td><td>Blyth</td><td>SA</td><td>200/400</td><td>2025</td><td>Construction</td></tr><tr><td>20</td><td>Bungama</td><td>SA</td><td>150/300</td><td>2026</td><td>ARENA Funding</td></tr><tr><td>21</td><td>CIS Capacity</td><td>SA</td><td>150/600</td><td>2027</td><td>CIS funding</td></tr><tr><td>22</td><td>Fulham BESS</td><td>VIC</td><td>64.8/116</td><td>2024</td><td>VRET</td></tr><tr><td>23</td><td>Koorangie BESS</td><td>VIC</td><td>185/370</td><td>2024</td><td><eq>System\ Strength\ Provision^{3}</eq></td></tr><tr><td>24</td><td>Rangebank BESS</td><td>VIC</td><td>200/400</td><td>2025</td><td>Committed</td></tr><tr><td>25</td><td>Derby BESS</td><td>VIC</td><td>85/100</td><td>2026</td><td>VRET</td></tr><tr><td>26</td><td>Melbourne Renewable Energy Hub</td><td>VIC</td><td>600/1600</td><td>2026</td><td>Committed</td></tr><tr><td>27</td><td>Gnarwarre BESS</td><td>VIC</td><td>290/550</td><td>2026</td><td>ARENA Funding</td></tr><tr><td>28</td><td>Horsham BESS</td><td>VIC</td><td>50/100</td><td>2026</td><td>VRET</td></tr><tr><td>29</td><td>Kiamal BESS</td><td>VIC</td><td>150/300</td><td>2026</td><td>VRET</td></tr><tr><td>30</td><td>Mortlake BESS</td><td>VIC</td><td>300/600</td><td>2026</td><td>ARENA Funding</td></tr><tr><td>31</td><td>Jeeralang Battery/Wooreen (Latrobe/Yallourn)</td><td>VIC</td><td>350/1400</td><td>2027</td><td>Proposed</td></tr><tr><td>32</td><td>CIS Capacity</td><td>VIC</td><td>150/600</td><td>2028</td><td>CIS funding</td></tr><tr><td colspan="6">Other publicly announced battery projects not included in the modelling</td></tr><tr><td>33</td><td>Other batteries</td><td>NEM</td><td>~6063MW</td><td>-</td><td>Publicly announced</td></tr></table>


1) NSW Emerging Technology Program 2) Project has also been granted funding from ARENA 3) Awarded a 20-year support agreement with AEMO for the provision of system strength 


# Agenda

Wholesale market modelling overview 

II. Asset-specific economics analysis 

III. MLF analysis 

IV. Appendix 

1. Model input assumptions 

2. Modelling approach – Market, Grid and Battery 

3. System Incident and Island Events 

4. Glossary 

# Unique, proprietary, in-house modelling capabilities underpin Aurora’s superior analysis

Integrated Models 

![image](https://cdn-mineru.openxlab.org.cn/result/2026-05-14/72c3f3f8-bc83-40c3-9286-f83b8bcc13a3/e12b6f282ebc331dfa2b27dee8d7b921c8d3d78468e65c16f45d1b6a2087c5ea.jpg)


# INPUTS

![image](https://cdn-mineru.openxlab.org.cn/result/2026-05-14/72c3f3f8-bc83-40c3-9286-f83b8bcc13a3/ae010d45fd9923c2e62c9dfd49731e99f80a575b4fd6d0bca73ee457d1142600.jpg)


Technology 

![image](https://cdn-mineru.openxlab.org.cn/result/2026-05-14/72c3f3f8-bc83-40c3-9286-f83b8bcc13a3/756744ea52228154e849c4d7d1060f79fdc42ace50adbf54bf7f90e1659f4cec.jpg)


Policy 

![image](https://cdn-mineru.openxlab.org.cn/result/2026-05-14/72c3f3f8-bc83-40c3-9286-f83b8bcc13a3/6e6e931616fd9ac8cfbdbd21d93ca06f3c77b1789b2f5cc99e896f5241bbfe82.jpg)


Demand 

![image](https://cdn-mineru.openxlab.org.cn/result/2026-05-14/72c3f3f8-bc83-40c3-9286-f83b8bcc13a3/489922f700355a272581ca3f442e506f4249de1f625534a56e999f8d080a3c17.jpg)


Commodity prices1) 

![image](https://cdn-mineru.openxlab.org.cn/result/2026-05-14/72c3f3f8-bc83-40c3-9286-f83b8bcc13a3/89a63df165dae52e120937ba2e7a88d80e16783df42e5db081e43294db68713f.jpg)


Weather patterns 

![image](https://cdn-mineru.openxlab.org.cn/result/2026-05-14/72c3f3f8-bc83-40c3-9286-f83b8bcc13a3/873a25d7be16c7368392d892d7cdebc0d4eb7d3447a5c0da2564d7b9295edb17.jpg)


# Hourly dispatch model

▪ Iterative modelling 

▪ Dynamic dispatch of plant 

▪ Endogenous interconnector flows 

▪ Stochastic dynamic programming for hydro 

![image](https://cdn-mineru.openxlab.org.cn/result/2026-05-14/72c3f3f8-bc83-40c3-9286-f83b8bcc13a3/4ca70e7aa67a3ad1cbb1adb9e76eaf08129ba23ec252070cb72c66ec17054dbd.jpg)



Continuous iteration until an equilibrium is reached


# Investment decisions module

▪ Capacity market modelling 

▪ Capacity build / exit / mothballing 

▪ IRR / NPV driven 

▪ Detailed technology assessments 

![image](https://cdn-mineru.openxlab.org.cn/result/2026-05-14/72c3f3f8-bc83-40c3-9286-f83b8bcc13a3/e01991cf68d24bd706947b6fad5195904aee6a1f5086ef909b41223493dd5f9d.jpg)


# OUTPUTS

![image](https://cdn-mineru.openxlab.org.cn/result/2026-05-14/72c3f3f8-bc83-40c3-9286-f83b8bcc13a3/e3bd6a1dd132bb06db4ea8584f566da775f249a5db7d45eef14d5628be8b38e5.jpg)


Capacity mix 

![image](https://cdn-mineru.openxlab.org.cn/result/2026-05-14/72c3f3f8-bc83-40c3-9286-f83b8bcc13a3/1e960f9f7e496e1f7f8704ab0e648bd0d9c728b65216ba2c3d697092b3a0e6f4.jpg)


Generation mix 

![image](https://cdn-mineru.openxlab.org.cn/result/2026-05-14/72c3f3f8-bc83-40c3-9286-f83b8bcc13a3/b5c7f9b8b95df2422872ab3a6d67168c538253862f01cbf5f05065ef8b2413fb.jpg)


Wholesale & imbalance prices 

![image](https://cdn-mineru.openxlab.org.cn/result/2026-05-14/72c3f3f8-bc83-40c3-9286-f83b8bcc13a3/58cf74f1853f1cd873b06ed7ad809b5a18d035eff1d553255e8ef8e1edd2c248.jpg)


Capacity market prices 

![image](https://cdn-mineru.openxlab.org.cn/result/2026-05-14/72c3f3f8-bc83-40c3-9286-f83b8bcc13a3/0c1e7ed01adf84e3de7724ee8aeb14872bd1e8861cc60f947849585f360f97a5.jpg)


Profit / Loss and NPV 

![image](https://cdn-mineru.openxlab.org.cn/result/2026-05-14/72c3f3f8-bc83-40c3-9286-f83b8bcc13a3/b5c4c0c9c76aea9a7eb691ecd5476d83bcc291a6d0a49487b5e7788184aae545.jpg)


Electric vehicle charging 

# Advantages of Aurora approach

Aurora have invested heavily in developing our dispatch models since 2013 and believe they are the most sophisticated available 

Our models have been rigorously tested and refined in a wide range of client contexts 

▪ Flexible and nimble because we own the code 

▪ Transparent results 

▪ State-of-the-art infrastructure 

▪ Zero dependence on black-box thirdparty software (e.g. PLEXOS) 

▪ Constantly up to date through subscription research 

▪ Ability to model complex policy changes quickly 

# Aurora’s market model accounts for MLFs in capacity expansion decisions, which are a critical input to Aurora’s network model

![image](https://cdn-mineru.openxlab.org.cn/result/2026-05-14/72c3f3f8-bc83-40c3-9286-f83b8bcc13a3/961fdae1f976e063fe4c4b3aa8763021cfd6871836cf77664b2ded5038f27aa7.jpg)


# What is a Marginal Loss Factor and why does it matter?

# Description

A Marginal Loss Factor (MLF) represents the marginal electrical transmission losses between a connection point and the regional reference node (RRN) 

Each year, AEMO assigns a generation-weighted MLF is to each generator and load within the NEM approximate that asset’s relative impact on thermal losses on the transmission grid. 

▪ These factors are applied as a scaler multiple to revenues and are intended to provide a locational signal for investment – generally encouraging generators to locate close (electrically speaking) to significant load areas 

AEMO publish the MLFs for a single upcoming financial year at a time using the results of a year-ahead forecast. AEMO conducts this forecast using their Foreward Looking Loss Factor Methodology. Aurora endevours to replicate this methodology across our standard forecast horizon 

▪ The relationship between transmission losses and power is: 

???????????? ∝ ???????????? 

# Illustration of power flow losses

![image](https://cdn-mineru.openxlab.org.cn/result/2026-05-14/72c3f3f8-bc83-40c3-9286-f83b8bcc13a3/1f4b6284576bf180532824029c0dcd40373a8c37316ab96ff7c13267157284cb.jpg)


![image](https://cdn-mineru.openxlab.org.cn/result/2026-05-14/72c3f3f8-bc83-40c3-9286-f83b8bcc13a3/05f694130b9fce0e4c115f1ee01494ed00f7e13bdb339482908dac9546240af2.jpg)


# Overview of Marginal Loss Factors (MLFs)

▪ The NEM implements a locational signal intended to approximate an asset’s impact on the total thermal losses on the transmission system 

▪ These factors are applied as a scaler multiple to revenues and are intended to provide a locational signal for investment – generally encouraging generators to locate close (electrically speaking) to significant load areas 

Thus, areas where local load is greater than local generation often have a generation MLF greater than 1.0, 

▪ Similarly, areas where local load is less than local generation likely have an MLF less than 1.0 

Each generator’s price bid to generate electricity is divided by the MLF at the generator’s connection point, while the price recovered by a generator is the Regional Reference Node (RRN)1 price multiplied by the same MLF 

▪ The MLF for each generator affects both the generator’s revenue as well as the generator’s position in the merit order. AEMO calculates the annual MLF, at each transmission connection point in the NEM, one financial- year ahead 

Given that MLFs are only published one year ahead, and are highly susceptible to the impact of individual plant connections/closures, recent market participants have seen large changes of +/- 10-20% in annual revenues from one year to the next 

Aurora provides an indicative MLF forecastby Renewable Energy Zone (REZ) as part of its core subscription package aiming to provide market participants with a long term view on MLFs and the key factors that might impact asset outcomes in the future 


Losses across a transmission line


![image](https://cdn-mineru.openxlab.org.cn/result/2026-05-14/72c3f3f8-bc83-40c3-9286-f83b8bcc13a3/62a9ba76918c3b91250b556f2226e052807282898439610ada6ef8f5b7843532.jpg)



Relationship between bidding, dispatch & settlements


![image](https://cdn-mineru.openxlab.org.cn/result/2026-05-14/72c3f3f8-bc83-40c3-9286-f83b8bcc13a3/e241e995b7e7c04ce9da07dc799cf474618233aec6392030c8fbafee1bd56590.jpg)


# The process for determining marginal loss factors

# AEMO’s MLF methodology:

MLFs are calculated according to AEMO’s Forward Looking Loss Factor process which can be broken out into the following key steps: 

▪ Data collection for:1 

o Existing generators, load and network details 

o Add/edit new generators, load and network details to match the forecast financial year 

o Historical plant operation and load profiles from the most recent full financial year 

▪ 2 Run the load flow model: 

o Following the process of minimal extrapolation of historical data to balance the forecast demand and supply 

o For each of the 17,520 half hours in the year 

▪ Rerun the load flow model:3 

o Shift 1MW of load from the RRN to the node of interest 

o Following the process of minimal extrapolation of historical data to match the forecast demand for the upcoming financial year 

o For each of the 17,520 half hours in the year 

▪ Calculate the MLF for each half hour:4 

o From the difference in losses between steps 2 & 3 

▪ Calculate the static, volume-weighted MLF for the node5 

o Using the corresponding generation or load to volume weight 

![image](https://cdn-mineru.openxlab.org.cn/result/2026-05-14/72c3f3f8-bc83-40c3-9286-f83b8bcc13a3/78532b89f94b953e377f7a4796b3e6aa45f6abad72785e83b7613929dee72b4a.jpg)


$$
A n n u a l M L F = \frac {\sum (M L F _ {t} * G _ {t})}{\sum G _ {t}}
$$

AEMO’s forward looking loss factor methodology sets out the described steps in determining the marginal loss factors for each asset in the upcoming year 

■ Aurora’s network model is used in conjunction with this methodology and the outputs from Aurora’s main market model to determine asset-specific MLFs out to 2050 

# Aurora’s market model accounts for MLFs in capacity expansion decisions, which are a critical input to Aurora’s network model

![image](https://cdn-mineru.openxlab.org.cn/result/2026-05-14/72c3f3f8-bc83-40c3-9286-f83b8bcc13a3/3ae607134ae0dc463c31c5f722ac6b02df84a421b7f618e2f5f7575df790e201.jpg)


# Aurora employs an integrated approach to endogenously modelling MLFs and their impact on each REZ

# Aurora’s approach to MLF modelling of REZs

▪ A range of factors affect how MLFs for each connection point evolve over time: 

Generation changes 

- Load profile changes 

- Upgrades and proximity to the high voltage network 

- Inter-regional and intra-regional flows 

▪ Aurora’s Central scenario includes an indicative MLF forecast for each REZ based on the effects of future generation changes. 

▪ Aurora incorporates AEMO guidelines on MLF robustness, wind and solar resource potential and quality, spare network capacity, potential network upgrade costs and effects for each REZ. 

This approach allows Aurora’s model to endogenously determine new, economically viable capacity decisions, per REZ, which incorporate the impact of changing MLFs that new capacity additions result in. 

▪ The detailed inputs for each REZ are provided in full detail in the databook accompanying this report. 


Illustration of endogenous MLF approach,


![image](https://cdn-mineru.openxlab.org.cn/result/2026-05-14/72c3f3f8-bc83-40c3-9286-f83b8bcc13a3/324270b604ae78128a5fac3bfd4209487095eec0597be9b33e17e393d2e3b1c0.jpg)


# Overview of FCAS cost recovery calculation methodology

# Regulation FCAS recovery (FCAS Causer Pays)1

▪ FCAS Causer Pays costs are charged to market generators and customers to recover Regulation FCAS costs. 

# Aurora’s FCAS Causer Pays equation:

Regulation FCAS Recovery = Global cost of Regulation FCAS requirement x Individual causer pays contribution factor 

▪ An individual’s market participant contribution factor represents the proportion of Regulation FCAS for which a market participant is liable. 

▪ These causer pays contribution factors are calculated based on metered asset performance (e.g. deviations in actual generation from dispatch targets) and are determined on the previous 28-day period. 

Aurora estimates an individual asset causer pays factor by extracting the historical market participant factors published by AEMO for each 28-day period and constructing a technology and region-specific causer pays factor based on the last 30 months of data. 

To support the calculation of FCAS Causer Pays recovery costs for an individual asset, and in line with Aurora’s approach of forecasting global FCAS requirements, we assume that: 

− The cost of Regulation FCAS requirements is not differentiated across regions 

− All market participants have metering sufficient to identify frequency performance – as such, FCAS Regulation residual recovery isn’t modelled 

# Raise Contingency FCAS recovery1

▪ Raise Contingency (RC) FCAS recovery costs are charged to market generators and market small generation aggregators to recover RC costs. 

# Aurora’s Raise Contingency (RC) Recovery equation:

RC FCAS Recovery = Global cost of RC FCAS requirement x Individual proportion of total NEM generation 

Aurora’s power market forecast model calculates total NEM-wide generation in half-hourly intervals. As such, individual asset contribution to total NEM-wide generation can be calculated for each time interval. 

▪ Additionally, all Raise Contingency FCAS market prices and procurement are calculated and aggregated up to half-hourly intervals. 

Therefore, Aurora can use asset-specific generation profiles to forecast Raise Contingency Recovery costs aggregated up from half-hourly inputs. 

In line with Aurora’s approach of forecasting global FCAS requirements, we assume that the cost of RC FCAS requirements is not differentiated across regions. 

▪ Lower Contingency FCAS costs are not considered as they are only charged to market customers. 

# There are two main revenue streams for a battery or PHES to make merchant revenues

# Energy arbitrage

▪ This is essentially a ‘buy low, sell high’ strategy 

▪ It involves buying energy in the NEM wholesale market at lower price periods and selling at higher prices periods 

▪ This trading strategy involves cycling the battery and therefore uses up finite battery cycles, degrades the battery, and due to round-trip efficiencies being less than 100%, requires more energy to be bought than can be sold 

▪ As such, the ‘price spread’ between the buy and sell price would need to be sufficiently high to cover these factors 

# FCAS markets

▪ This involves offering the battery’s capacity (i.e. its MW of charge and/or discharge) into one of the NEM’s ten FCAS markets (frequency control ancillary services) 

Under FCAS markets, assets get an availability payment for being on standby i.e. they are paid even if they are not called upon to provide any energy 

▪ If a battery has been enabled in a FCAS market (and hence is getting the availability payment) and it is called upon, it also gets paid for the energy it discharges (or must pay for the energy it charges) 

# Practical battery operation in the NEM

▪ For a battery to be deployed in the NEM, it bids its capacity into the market for every 5-minute period (as do all scheduled generators) 

▪ A battery may offer bids for its capacity to buy/sell in the wholesale energy market and/or supply standby capacity in one/multiple FCAS markets 

AEMO then aggregates the energy and FCAS bids of all generators across the NEM and co-optimizes the combination of generators to meet the need for wholesale energy and FCAS services at least system cost (subject to system security constraints and the physical limits on the system) 

▪ If a battery’s bids were competitive, it will then receive a dispatch instruction from AEMO for the 5-minute period 

# Batteries: Overview of Aurora dispatch methodology

# 1 Description & Assumptions

▪ Battery margins represent assets under a purely energy trading business model, buying and selling power in the wholesale and FCAS markets, based off our market forecast generated prices 

Cycling rates are chosen to represent what a typical asset might target, actual rates will vary according to business model, financing consideration, battery warranty agreements and market conditions. Cycling rate limitations are applied to total yearly cycles, i.e., volume is not capped on any individual day 


Key parameters


<table><tr><td>Durations considered</td></tr><tr><td>Cycles considered</td></tr><tr><td>Market access</td></tr></table>


Value


<table><tr><td>Typically 1hr, 2hr, 4hr duration</td></tr><tr><td>Typically 1x, 1.5x &amp; 2x per day</td></tr><tr><td>Wholesale, Regulation and Contingency Markets</td></tr></table>


Key Assumptions


<table><tr><td>Round-trip efficiency</td></tr><tr><td>Assumed dispatch - regulation markets</td></tr><tr><td>Assumed dispatch - contingency markets</td></tr></table>


Value/comment


<table><tr><td>Varies based on manufacturer</td></tr><tr><td>18/8%</td></tr><tr><td>0%</td></tr></table>

# 2 Energy Trading Strategy Overview

▪ The asset trades in the wholesale market and the regulation and contingency FCAS markets 

▪ The asset has foresight into the market prices for 1 day and uses that to determine prices to charge and discharge at 

▪ When trading, the asset can choose to charge or discharge in the wholesale market or whether to provide regulation or contingency services. The trade-off between wholesale, regulation and contingency takes into account the expected charge or discharge in each market and the implications for cycles 

# 3 Key terms

▪ Cycles: volume of charging/discharging in terms of equivalent full cycles 

▪ Duration: ratio of MWh to MW for the asset, in hours 

Gross Margin: net trading profit from buying and selling power in the wholesale, regulation and contingency markets only; does not include any fixed charges, additional variable costs or benefits that may apply or other cashflows 

▪ FCAS capacity revenue: capacity payments only from asset’s procurement in the relevant FCAS markets, this does not include the asset’s revenue from actual dispatch/charge as a result of its procurement in FCAS markets 

# Our dispatch model heuristic trades between wholesale, regulation and contingency markets


Overview of trading heuristic:


![image](https://cdn-mineru.openxlab.org.cn/result/2026-05-14/72c3f3f8-bc83-40c3-9286-f83b8bcc13a3/e7271c3e60818781048b02b32e3938ebc0d072fb5b851e129b1641a1612fa16d.jpg)


Sell threshold and buy threshold represent the lowest and highest price at which the battery is willing to sell and buy power. As battery has imperfect foresight, the thresholds are determined based on the available spread that the battery can capture in the WM only. 

Buy and sell thresholds represent the value of the ability to charge or discharge and can therefore be used to calculate the value of regulation and contingency trades 

When calculating the value of combining market position, the model iterates over all possible combinations of the profitable trades within market rules/limits. 

# Grid-scale batteries derive revenues from selling energy into wholesale markets and capacity into FCAS markets

![image](https://cdn-mineru.openxlab.org.cn/result/2026-05-14/72c3f3f8-bc83-40c3-9286-f83b8bcc13a3/4fd4981c28b618e0fa7bb11abf3cb8de44beb7cf796f49a7879200d176f3eebe.jpg)


Wholesale gross margin ($) 

FCAS gross margin ($) 

= Wholesale sell ($) – wholesale buy ($) + energy sold providing regulation raise ($) – energy bought providing regulation lower ($) 

= Regulation capacity payment ($) + Contingency capacity payment ($) 

# Aurora’s in-model battery degradation provides more accurate results than out-of-model degradation

When a battery is operated, its performance gets slightly worse after each cycle. In particular, the amount of energy the battery can store decreases. This process is called battery degradation. There are two possible methods to account for degradation, Aurora uses in-model battery degradation, which is the most accurate. 

# Out-of-model battery degradation

• The battery makes hourly dispatch decisions based on its full duration 

• Model outputs are corrected to account for degradation. A degradation factor, based on the number of cycle that the battery has performed, is applied to battery exported volumes and revenues 

Example: 1 MW, 16th year of operation, degradation factor of 0.0055% per cycle in the first 3 years of operation and 0.0041 % per cycle thereafter 

Duration = 2hr Energy arbitrage (EA) gross margin = $115.8/kW EA gross margin (with degradation) = EA gross margin * 0.7811 = $90.4/kW 

# In-model battery degradation

At the beginning of each day, the effective duration of the battery is calculated. A degradation factor is applied, based on the number of cycles that the battery has performed until that day 

The battery makes more optimized hourly dispatch decisions based on its degraded duration 

Example: 1 MW, 16th year of operation, degradation factor of 0.0055% per cycle in the first 3 years of operation and 0.0041 % per cycle thereafter 

Duration = 2hr Average degraded duration = Duration * 0.7811 = 1.56hr Energy arbitrage gross margin (with degradation) = $104/kW 


EA export volume (16th year of operation)


![image](https://cdn-mineru.openxlab.org.cn/result/2026-05-14/72c3f3f8-bc83-40c3-9286-f83b8bcc13a3/0bd449a0d38997acaf8fa45a893a6838e71fc20e969287bb6e857bfab33e02d1.jpg)



EA gross margin (16th year of operation)


![image](https://cdn-mineru.openxlab.org.cn/result/2026-05-14/72c3f3f8-bc83-40c3-9286-f83b8bcc13a3/367591230cd1b368c8dabfcbbc21d7940182f8bc0c273d407252b871ce974951.jpg)


When using in-model degradation, the battery knows its duration and can pick the best hours for buying and selling. In the example, the battery chooses to dispatch more in the balancing market, because it is more profitable. 

# Battery dispatch model considers trading opportunities in both wholesale and FCAS markets simultaneously

Simplified illustration of battery dispatch model 

![image](https://cdn-mineru.openxlab.org.cn/result/2026-05-14/72c3f3f8-bc83-40c3-9286-f83b8bcc13a3/4c9a5f2df3ac263782aece66e755241f86596a46c32af675b16bff2cc1679720.jpg)



1) Simplified example displaying only wholesale, raise and lower regulation FCAS prices for clarity. In the actual modelling exercise, we consider Contingency markets as well.


# Illustrative

# Aurora battery dispatch model

Aurora’s battery dispatch model adopts a heuristic imperfect foresight methodology which dispatches against wholesale and FCAS markets 

# This incorporates:

▪ opportunity cost of FCAS participation 

▪ load and generation MLFs 

▪ asset capabilities 

An example two-day dispatch: 

Participating in lower reg, and possibly using the expected dispatch to charge 

B Battery charges as wholesale price turns negative 

Battery slowly discharges through its participation in FCAS raise regulation 

# Agenda

Wholesale market modelling overview 

II. Asset-specific economics analysis 

III. MLF analysis 

IV. Appendix 

1. Model input assumptions 

2. Modelling approach – Market, Grid and Battery 

3. System Incident and Island Events 

4. Glossary 

# Aurora has categorised historic events which drive above-average BESS returns into three categories – typical volatility, minor events, and major events

# Included in Aurora Market Forecast

# Typical volatility

Historic volatility, generally under system-normal conditions, where a handful of $1,000+ prices occur 

# Drivers

▪ Weather (e.g. excessively hot afternoons and cold winters) 

Network constraints constraining off interconnection and cheaper generation 

▪ Above-SRMC bidding 

▪ Move to 5-minute settlement 

Additional renewable build and exit of baseload (such as Liddell) 

# Modelling approach

Included in forecast scenarios as a part of Aurora’s “peak volatility” forecast 

Aurora Central is calibrated on FY18-21 NEM volatility, with more recent experience to flow through when there is more market data available 

# Examples

▪ VNI constraints leading to economic islanding 

▪ Lack of reserve (LOR) conditions 

▪ AEMO intervention pricing + RERT 

▪ Queensland heatwave (Jan 2017) 

# Minor events1

Volatility under “minor”, non-credible system contingencies and events; typically, a few days to a week of volatile prices 

# Drivers

▪ Network outages, such as those caused by lightning or natural disaster 

▪ Unexpected accidents causing explosion or fire within a power plant 

Equipment failures, electric faults due to age, lack of maintenance/protection, etc. 

# Modelling approach

These events are unpredictable high impact, low probability by nature and excluded from Aurora forecast scenarios 

▪ Aurora has identified multiple events and undertaken historical back-casting to identify revenue upside 

Optional overlay of revenue upside in storage gross margin analysis 

# Examples

▪ QNI planned outages, QLD (Oct 2021 – Mar 2022) 

▪ Torrens Island transformer fire, SA (Mar 2021) 

▪ Australian Bushfires, NSW (Jan 2020) 

▪ Victorian blackouts (Jan 2019) 

# Major events1

Volatility under “major”, non-credible system contingencies and events; impacts up to and in excess of a month 

# Drivers

Same as minor events, but larger in magnitude/impact. May lead to multiday state frequency islanding, for example 

# Modelling approach

▪ Same as “minor events” 

# Examples

▪ Tailem Bend outage, SA (Nov 2022) 

▪ Callide C explosion, QLD (May 2021) 

▪ Heywood interconnector outage, SA (Jan-Feb 2020) 

# Aurora has categorised historic events which drive above-average BESS returns into three categories – typical volatility, minor events, and major events

# Included in Aurora’s Market Forecasts

# Typical volatility

# Example

VNI constraints (May 2023) 

Network constraints on VNI limiting the ability of Victorian generators to supply NSW and vice versa 

![image](https://cdn-mineru.openxlab.org.cn/result/2026-05-14/72c3f3f8-bc83-40c3-9286-f83b8bcc13a3/ad795c37169d8b3114aca216e94a410389e8f729299575a7b7997d404e952264.jpg)


# Minor events1

# Examples

Torrens Island, SA (March 2021) 

▪ A planned network outage near the Heywood interconnector invoked local SA FCAS requirements 

Fire at Torrens Island power station leading to trip of Torrens A West and Torrens B West 

Existing local FCAS volatility exacerbated by significant loss of generation 


SA FCAS L60 prices – 12 March 2021


![image](https://cdn-mineru.openxlab.org.cn/result/2026-05-14/72c3f3f8-bc83-40c3-9286-f83b8bcc13a3/3dcc5416411ea490d43165246fce6f78b91b413498cb62a0fe09c6af2630cc69.jpg)


# Major events1

# Example

Tailem Bend, SA (November 2022) 

Lightning strike caused network outage at Tailem Bend in SA, frequency islanding the state for ~7 days 

Batteries west of the outage achieved outsized revenues; Dalrymple (below) achieved ~6 months of merchant revenue in the week of islanding 


Dalrymple (SA) revenues ($/MW) – 10-18 November 2022


![image](https://cdn-mineru.openxlab.org.cn/result/2026-05-14/72c3f3f8-bc83-40c3-9286-f83b8bcc13a3/d31c1cbaea3b19bdfc3470cece7fd13b1e5e465a4ac692b000911438fbe5421b.jpg)


# In the last 3 years, we have seen on average 2 – 3 minor and major events each year; these have resulted in notable price shocks


Historic wholesale prices



A$/MWh, real 2022


![image](https://cdn-mineru.openxlab.org.cn/result/2026-05-14/72c3f3f8-bc83-40c3-9286-f83b8bcc13a3/9d4bb86fbc7dace246cba095a778ac7404cacd195630d2188da62f7521f75ceb.jpg)



Historic FCAS prices



A$/MW/h, real 2022


![image](https://cdn-mineru.openxlab.org.cn/result/2026-05-14/72c3f3f8-bc83-40c3-9286-f83b8bcc13a3/b84d0a1274849aea4f55309a7c30abf3a162e9a6ece0fc53a812a51d42dcaaa1.jpg)


![image](https://cdn-mineru.openxlab.org.cn/result/2026-05-14/72c3f3f8-bc83-40c3-9286-f83b8bcc13a3/be5e81f5b6e2edf91fe9e1a9dbbcd4392e3531ffc50344badf032499c33a4aab.jpg)



1) Aurora’s categorisation of ‘major’ and ‘minor’ events includes out-of-equilibrium system events that lead to outsized battery returns in wholesale and/or FCAS markets. System incidents that are short-lived and have minimal market impact are not considered ‘major’ or ‘minor’ events, and are not removed from Aurora’s typical volatility calibration. AEMO reported 36 and 20 system incidents in 2021 and 2022, many of which had minimal impact on wholesale and FCAS markets.


We have seen a number of very high price events in the NEM in recent years. These events offer significant upsides to BESS revenues 

Aurora has called out multiple system events that have driven battery revenues: 

Minor events –are times where volatility is driven by atypical system events; often the separation of FCAS markets 

Major events –are times where volatility is driven by system events, but where the effects are longer lasting and are of a greater magnitude of cost. Major events have often created frequency islands in the NEM resulting in extreme FCAS prices, or extended periods of scarcity of supply and high wholesale volatility 

# Day-to-day volatility has also been increasing – the rise in ‘Lack of Reserve’ conditions signals potentially tighter capacity margins

<table><tr><td rowspan="2" colspan="2"></td><td colspan="3">Count of Lack of Reserve (LOR) market notices</td></tr><tr><td>LOR1</td><td>LOR2</td><td>LOR3</td></tr><tr><td rowspan="4">2017</td><td>NSW</td><td>5</td><td>1</td><td>1</td></tr><tr><td>QLD</td><td>1</td><td>1</td><td>0</td></tr><tr><td>SA</td><td>7</td><td>5</td><td>1</td></tr><tr><td>VIC</td><td>2</td><td>0</td><td>0</td></tr><tr><td rowspan="4">2018</td><td>NSW</td><td>11</td><td>3</td><td>0</td></tr><tr><td>QLD</td><td>3</td><td>0</td><td>0</td></tr><tr><td>SA</td><td>3</td><td>0</td><td>0</td></tr><tr><td>VIC</td><td>3</td><td>1</td><td>0</td></tr><tr><td rowspan="4">2019</td><td>NSW</td><td>3</td><td>0</td><td>0</td></tr><tr><td>QLD</td><td>1</td><td>0</td><td>0</td></tr><tr><td>SA</td><td>1</td><td>1</td><td>0</td></tr><tr><td>VIC</td><td>5</td><td>3</td><td>2</td></tr><tr><td rowspan="4">2020</td><td>NSW</td><td>21</td><td>5</td><td>0</td></tr><tr><td>QLD</td><td>0</td><td>0</td><td>0</td></tr><tr><td>SA</td><td>0</td><td>1</td><td>0</td></tr><tr><td>VIC</td><td>1</td><td>2</td><td>0</td></tr><tr><td rowspan="4">2021</td><td>NSW</td><td>39</td><td>4</td><td>0</td></tr><tr><td>QLD</td><td>12</td><td>2</td><td>0</td></tr><tr><td>SA</td><td>5</td><td>2</td><td>0</td></tr><tr><td>VIC</td><td>2</td><td>0</td><td>0</td></tr><tr><td rowspan="4">2022</td><td>NSW</td><td>32</td><td>10</td><td>0</td></tr><tr><td>QLD</td><td>49</td><td>10</td><td>0</td></tr><tr><td>SA</td><td>19</td><td>1</td><td>0</td></tr><tr><td>VIC</td><td>3</td><td>2</td><td>0</td></tr></table>

# AUR RA

Lack of Reserve notices are issued by AEMO when forecast instantaneous capacity margin falls below the largest generating units in a state, signalling a scarcity of supply and often associated with very high/market cap wholesale prices 

LOR1 is the least severe, triggered when reserve levels fall below the two largest supply resources and acts as a market signal to bring on more supply or reduce demand 

LOR2 conditions exist when reserve falls below the single largest supply resource, and allows AEMO to provide directions to generators and activate Reliability & Emergency Reserve Trader (RERT) 

LOR3 is generally quite rare, signalling a deficit in supply, possibly leading to controlled load shedding 

The volume of notices issued to the market, and instances of scarce supply, increased significantly in 2021-22, particularly in Queensland an NSW following the explosion of Callide C and other system events, bringing about unprecedented levels of wholesale volatility 

LOR events can coincide with major and minor events, but often arise under system normal conditions such as hot afternoons, which are included in Aurora’s typical volatility forecast 

# Batteries across all states can benefit from peak pricing events, even if the event did not occur in the state itself


Aurora modelled 2hr BESS quarterly gross margin


![image](https://cdn-mineru.openxlab.org.cn/result/2026-05-14/72c3f3f8-bc83-40c3-9286-f83b8bcc13a3/48470f44a70945e15511e5a7e81b86469e8fee5f8c04f1c5565a294407e42b18.jpg)


Whilst islanding events are a key driver of higher revenues, upsides need not be limited to the state where these events occur 

We have seen several examples in the past where a high price volatility event in one state affects other states (either through the FCAS or wholesale markets) 

▪ There are two main events into which we will deep dive: 

1) 2021 Q2 – QLD sees high peak price revenues due to Callide C explosion, with some flow on effects for NSW and Vic 

2) 2022 Q4 – An SA BESS could have seen high regulation revenue due to Tailem Bend islanding event 

# QLD Callide C4 outage deep-dive: sudden reduction in low-price baseload generation could have boosted a battery’s revenues significantly


Aurora modelled 2hr QLD BESS monthly gross margin



A$/kW nameplate, real 2022



Intraday 2hr price spread



A$/MWh, real 2022


![image](https://cdn-mineru.openxlab.org.cn/result/2026-05-14/72c3f3f8-bc83-40c3-9286-f83b8bcc13a3/27924ed55d0982d8d7e25568a8f1d8318b970ba226119770a1407df7a425823a.jpg)


# AUR RA

On 25 May 2021, a catastrophic failure of Callide C unit 4 reduced the amount of low-price baseload generation, which combined with the reduced output of Stanwell and Gladstone power stations resulted in a reduction of ~2,000 MW capacity 

Besides, the planned outage of QNI interconnector also limited QLD’s ability to import cheaper generation (e.g., baseload and renewable generation) from NSW 

Consequently, QLD’s highest wholesale price exceeded $5,000/MWh for a few trading intervals with 2h price spread exceeding $900/MWh for May and June, which would have enabled a QLD battery to achieve significantly higher revenues. In particular, the percentage of battery’s peak-price revenue increases from 7% to 42% in May 2021 

With Callide staying offline post May 2021, QLD’s battery continues to see high revenues. However, the proportion of peak-price revenues dropped following the immediate aftermath in June, dropping further in July, due to lucrative opportunities in elevated contingency markets 

# The Tailem Bend line outage enabled two SA batteries to earn ~6 months of revenue in a week


Tailem Bend outage – 12 to 19 November 2022


![image](https://cdn-mineru.openxlab.org.cn/result/2026-05-14/72c3f3f8-bc83-40c3-9286-f83b8bcc13a3/1e930db2c1645ca5e97ab6171dcdcad332b8c857cb6e0ade9a85299c40056ec5.jpg)



Approx. 5 hours later at 21:30, AEMO invoked constraints separating Lake Bonney from SA and then constraints at 2:40 on 13 November removing Lake Bonney’s ability to provide FCAS


![image](https://cdn-mineru.openxlab.org.cn/result/2026-05-14/72c3f3f8-bc83-40c3-9286-f83b8bcc13a3/922393233fbed020d485aba30b40d571113d0e9e3b3958c6b98370edca59e09b.jpg)



1) Gross margins shown for Lake Bonney calculated based on SA wholesale and FCAS prices. Islanding revenues between 12 and 18 November may differ when Lake Bonney was physically separated from SA.


# Frequency of upside events are higher in QLD/SA; a minor event earns ~$7m for a 100MW BESS, while a major event adds ~$24m

![image](https://cdn-mineru.openxlab.org.cn/result/2026-05-14/72c3f3f8-bc83-40c3-9286-f83b8bcc13a3/75e26c7e0dc0ccc0491078f8bf69a9f13810420f6f08ecef96809a169bf67951.jpg)



2hr battery monthly gross margin during system events (2018-2022)


![image](https://cdn-mineru.openxlab.org.cn/result/2026-05-14/72c3f3f8-bc83-40c3-9286-f83b8bcc13a3/f2a7b11a13d69c4166fb641b03544a3a36d937fc8d69c882a9f540bd8ee9914e.jpg)



1) Assumes 30-day month and 1-cycle-per-day. 2) Aurora Q2 2023 capex for a 2024-entry, 2-hour battery.


# AUR RA

‘Major’ and ‘minor’ system events have shown to be major contributors to battery gross margins over the past few years 

Aurora has identified 18 individual ‘minor’ events and 4 ‘major’ events over the past 6 years, across the NEM 

Queensland and SA have seen the greatest number of these events due to their proximity at the edge of the NEM and tendency to both frequency and economically island from the rest of the NEM 

Victoria and NSW have seen less frequent ‘minor’ events – 1-in-3 years on average – and no ‘major’ events; however, upsides have typically been in wholesale volatility triggered by capacity shortfalls 

Given Victoria and NSW’s reliance on ageing thermal baseload, coupled with current and forecasted system tightness in NSW, worsening coal reliability could contribute to the future frequency of events 

The average magnitude of events between 2018 and 2022 works out at $73/kW for ‘minor ‘ (~6% of capex1) and $241/kW for ‘major’ events (~20% of capex2) 

Aurora has excluded 2017 events as there were no batteries in the market at this time 

# Agenda

Wholesale market modelling 

II. Asset-specific economics analysis 

III. Gross margin analysis 

IV. MLF analysis 

V. Appendix 

1. Background on Battery Storage Modelling 

2. System Incident and Island Events 

3. Modelling approach – Market, Grid and Battery 

4. Glossary 

# Explanation of key concepts [1/2]

<table><tr><td>Key Terms</td><td>Description</td></tr><tr><td>TWA</td><td>The time-weighted average price is the simple average of all half hourly prices during a given period</td></tr><tr><td>DWA</td><td>Dispatch-weighted average price is the average of the regional reference node price achieved by an asset (or type of technology) where the average price is weighted by the asset&#x27;s generation in a given periodThere are a number of different ways of defining the dispatch-weighted average prices. Aurora&#x27;s forecast DWA prices are defined as follows:-Pre-MLF and Post-Curtailment-This means that losses due to MLFs are not accounted for and assumes that assets economically curtail at 0$/MWh to avoid negative prices-Pre-MLF and Pre-Curtailment-This means that losses due to MLFs are not accounted for and assumes that assets still generate through negative price periodsFinal asset revenues can then be calculated according to the following formula:-[Post-curtailment final revenues] = [Pre-mlf, post-curtailment DWA] x [MLF] x [(1 - curtailment rate) x Pre-Curtailment Generation]-[Pre-curtailment final revenues] = [Pre-mlf, pre-curtailment DWA] x [MLF] x [Pre-Curtailment Generaiton]</td></tr><tr><td>Price cannibalisation</td><td>Price cannibalisation is the price impact of high levels of zero-marginal cost renewable generation on dispatch-weighted prices. When solar and wind output is high, it tends to bring down prices in those periods as lower cost technologies set the margin in the wholesale market (&#x27;merit order effect&#x27;)</td></tr><tr><td>Inflation</td><td>Aurora&#x27;s forecast prices are published in real 2022 calendar year prices as at <eq>30^{th}</eq> June 2022. Aurora models all forecasts in real terms and provides the International Monetary Fund&#x27;s future CPI expectation as a possible metric to use to convert our forecasts to nominal terms. However, CPI has not historically been strongly and consistently correlated with electricity prices and Aurora&#x27;s subscribers typically apply a range of in-house views on future inflation rates</td></tr><tr><td>Financial years</td><td>Aurora&#x27;s forecasts are in financial years and follow the federal financial year (1 July to 30 June). Years refer to the end of the financial year, so e.g. FY 2026 refers to 30 June 2025 to 1 July 2026</td></tr><tr><td>Reference weather years</td><td>Aurora&#x27;s half-hourly renewable generation and demand traces are based on the FY2016 reference weather year. The alignment of each of these input traces to the same reference weather year is critical due to the impact that weather has on renewable generation and demand, and the knock-on impact on half-hourly wholesale prices</td></tr></table>

# Explanation of key concepts [2/2]

<table><tr><td>Key Terms</td><td>Description</td></tr><tr><td>LGCs</td><td>Large-scale generation certificates (LGCs) are created on a yearly basis based on the amount of power generated by an accredited and registered renewable energy power station. An LGC represents one megawatt hour (MWh) of net renewable energy generated. Registered LGCs can be sold or transferred to entities with liabilities under the Renewable Energy Target or other companies looking to voluntarily surrender LGCs</td></tr><tr><td>LCOE</td><td>The levelised cost of electricity (LCOE) is the NPV of the unit-cost of electrical energy over the lifetime of a generating asset. It is effectively a simplified assessment of the cost competitiveness of an electricity-generating system that incorporates all costs over an asset&#x27;s lifetime: initial investment, operations and maintenance, cost of fuel, cost of capital</td></tr><tr><td>MLFs</td><td>Marginal loss factors (MLFs) reflect the impact of electricity losses along the network and are applied to market settlements in the National Electricity Market (NEM), and so affect generator revenues. They represent electricity losses along the transmission network between a connection point and the regional reference node (RNN), which is used to represent the regional centre of the transmission network</td></tr><tr><td>Non-volatile / fundamental prices</td><td>Aurora&#x27;s standard power market model only includes “fundamentals-based” volatility and therefore the half-hourly prices do not include extreme price events above approximately $1,000/MWh (as these typically cannot be explained by generator SRMC / shadow pricing)</td></tr><tr><td>“Typical volatility” prices</td><td>Revenues from +$1,000/MWh price periods are a material factor in the investment case of flexible assets, such as batteries. To capture this market feature, Aurora has a fourth step to price formation (not to be confused with “uplift” which is the second step to price formation). This fourth step is a “post-model” process to add +$1,000/MWh price periods in line with what has been seen historically over the last 3-5 years in each state (but excluding any major/minor system incidents from the calibration – hence the term “typical” volatility, as this approach does not try to recreate persistent, significant market events that may be driven by long-term network outages or coal plant explosions). This “post-model” processing involves using a stochastic (Markov Chain) approach where spiky prices are probabilistically added to half-hours according to spare capacity margin in that half-hour.</td></tr></table>

# Glossary of key NEM and modelling terms [1/2]

<table><tr><td>Abbreviation</td><td>Explanation</td></tr><tr><td>A$</td><td>Australian Dollars (assumed to be real 2022 terms unless otherwise stated</td></tr><tr><td>ACCC</td><td>Australian Competition and Consumer Commission</td></tr><tr><td>AEMO</td><td>Australian Energy Market Operator</td></tr><tr><td>AER</td><td>Australian Energy Regulator</td></tr><tr><td>ASX</td><td>Australian Stock Exchange</td></tr><tr><td>BTM</td><td>Behind-the-Meter</td></tr><tr><td>Capex</td><td>Capital Expenditure</td></tr><tr><td>CIS</td><td>Capacity Investment Scheme</td></tr><tr><td>CM</td><td>Capacity Market</td></tr><tr><td>COAG</td><td>Council of Australian Governments</td></tr><tr><td>COD</td><td>Commissioning Date</td></tr><tr><td>CCGT</td><td>Combined Cycle Gas Turbine</td></tr><tr><td>CfD</td><td>Contract for Difference</td></tr><tr><td>CHP</td><td>Combined Heat and Power</td></tr><tr><td><eq>CO_{2}</eq></td><td>Carbon Dioxide</td></tr></table>

<table><tr><td>Abbreviation</td><td>Explanation</td></tr><tr><td>DLF</td><td>Distribution Loss Factor</td></tr><tr><td>DSP</td><td>Demand Side Participation</td></tr><tr><td>DWA</td><td>Dispatch Weighted Average</td></tr><tr><td>EIS</td><td>Emissions Intensity Scheme</td></tr><tr><td>ESB</td><td>Energy Security Board</td></tr><tr><td>ESOO</td><td>Electricity Statement of Opportunities</td></tr><tr><td>ETS</td><td>Emissions Trading Scheme</td></tr><tr><td>EVs</td><td>Electric Vehicles</td></tr><tr><td>FCAS</td><td>Frequency Controlled Ancillary Services</td></tr><tr><td>FOB</td><td>Free On Board</td></tr><tr><td>GJ</td><td>Gigajoule</td></tr><tr><td>GW</td><td>Gigawatt</td></tr><tr><td>kW</td><td>Kilowatt</td></tr><tr><td>LCOE</td><td>Levelised Cost of Energy</td></tr><tr><td>LGCs</td><td>Large-scale Generation Certificates</td></tr><tr><td>LRET</td><td>Large-scale Renewable Energy Target</td></tr></table>

# Glossary of key NEM and modelling terms [2/2]

<table><tr><td>Abbreviation</td><td>Explanation</td></tr><tr><td>LNG</td><td>▪ Liquefied Natural Gas</td></tr><tr><td>MLF</td><td>▪ Marginal Loss Factor</td></tr><tr><td>Mt</td><td>▪ Mega tonne (one million metric tonnes)</td></tr><tr><td>MWh</td><td>▪ Megawatt Hour</td></tr><tr><td>MW</td><td>▪ Megawatt</td></tr><tr><td>NEG</td><td>▪ National Energy Guarantee</td></tr><tr><td>NEM</td><td>▪ National Electricity Market</td></tr><tr><td>NSG</td><td>▪ Non-Scheduled Generation</td></tr><tr><td>Opex</td><td>▪ Operational Expenditure</td></tr><tr><td>PPA</td><td>▪ Power Purchasing Agreement</td></tr><tr><td>RES</td><td>▪ Renewable Energy System(s)</td></tr><tr><td>REGO</td><td>▪ Renewable Energy Guarantee of Origin</td></tr><tr><td>RRN</td><td>▪ Regional Reference Node</td></tr><tr><td>RRO</td><td>▪ Retailled Reliability Obligation</td></tr><tr><td>SRMC</td><td>▪ Short-Run Marginal Cost</td></tr><tr><td>TWA</td><td>▪ Time-weighted Average</td></tr><tr><td>TWh</td><td>▪ Terawatt Hour</td></tr><tr><td>WACC</td><td>▪ Weighted Average Cost of Capital</td></tr></table>

# General Disclaimer

This document is provided "as is" for your information only and no representation or warranty, express or implied, is given by Aurora Energy Research Limited and its subsidiaries Aurora Energy Research GmbH and Aurora Energy Research Pty Ltd (together, "Aurora"), their directors, employees agents or affiliates (together, Aurora’s "Associates") as to its accuracy, reliability or completeness. Aurora and its Associates assume no responsibility, and accept no liability for, any loss arising out of your use of this document. This document is not to be relied upon for any purpose or used in substitution for your own independent investigations and sound judgment. The information contained in this document reflects our beliefs, assumptions, intentions and expectations as of the date of this document and is subject to change. Aurora assumes no obligation, and does not intend, to update this information. 

# Forward-looking statements

This document contains forward-looking statements and information, which reflect Aurora’s current view with respect to future events and financial performance. When used in this document, the words "believes", "expects", "plans", "may", "will", "would", "could", "should", "anticipates", "estimates", "project", "intend" or "outlook" or other variations of these words or other similar expressions are intended to identify forward-looking statements and information. Actual results may differ materially from the expectations expressed or implied in the forward-looking statements as a result of known and unknown risks and uncertainties. Known risks and uncertainties include but are not limited to: risks associated with political events in Europe and elsewhere, contractual risks, creditworthiness of customers, performance of suppliers and management of plant and personnel; risk associated with financial factors such as volatility in exchange rates, increases in interest rates, restrictions on access to capital, and swings in global financial markets; risks associated with domestic and foreign government regulation, including export controls and economic sanctions; and other risks, including litigation. The foregoing list of important factors is not exhaustive. 

# Copyright

This document and its content (including, but not limited to, the text, images, graphics and illustrations) is the copyright material of Aurora, unless otherwise stated. This document is confidential and it may not be copied, reproduced, distributed or in any way used for commercial purposes without the prior written consent of Aurora. 

# AUR RA

ENERGY RESEARCH 