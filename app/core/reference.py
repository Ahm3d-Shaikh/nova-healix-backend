"""Static reference data served by /api/meta: disclaimer, data provenance, sources."""

from app.models.meta import DataProvenanceRow, SourceLink

DISCLAIMER = (
    "Decision support prototype, not a medical device. Crew data is simulated; space-weather data is real NASA data."
)

DATA_PROVENANCE: tuple[DataProvenanceRow, ...] = (
    DataProvenanceRow(
        data="Space weather events (SEP, flares, CME, storms, notifications)", status="real", source="NASA DONKI API"
    ),
    DataProvenanceRow(
        data="Radiation, CO2 and temperature limits", status="real", source="NASA-STD-3001 technical briefs"
    ),
    DataProvenanceRow(data="Neutron share and dose", status="real (published)", source="CSA Radi-N2"),
    DataProvenanceRow(
        data="Loneliness questions and scoring",
        status="real (validated)",
        source="Three-Item Loneliness Scale (Hughes et al., 2004)",
    ),
    DataProvenanceRow(
        data="Reaction test design and lapse rule", status="real (validated)", source="PVT-B (Basner et al., 2011)"
    ),
    DataProvenanceRow(
        data="Crew vitals, sleep, exercise, CO2/temperature readings, questionnaire answers, daily dose",
        status="simulated",
        source="Our seeded generator",
    ),
)

_NASA = "https://www.nasa.gov/wp-content/uploads"
SOURCES: tuple[SourceLink, ...] = (
    SourceLink(
        title="Challenge page",
        url="https://www.spaceappschallenge.org/2026/challenges/create-health-monitoring-software-for-astronauts-on-space-missions/",
    ),
    SourceLink(title="Judging & Awards Guide", url="https://www.spaceappschallenge.org/resources/judging-awards-guide"),
    SourceLink(
        title="NASA: The Human Body in Space (RIDGE)",
        url="https://www.nasa.gov/humans-in-space/the-human-body-in-space/",
    ),
    SourceLink(title="NASA DONKI API", url="https://ccmc.gsfc.nasa.gov/DONKI/api/"),
    SourceLink(
        title="NASA radiation protection brief", url=f"{_NASA}/2023/03/radiation-protection-technical-brief-ochmo.pdf"
    ),
    SourceLink(title="NASA CO2 brief", url=f"{_NASA}/2023/12/ochmo-tb-004-carbon-dioxide.pdf"),
    SourceLink(
        title="NASA CO2 brief (headache risk)",
        url="https://nasa.gov/wp-content/uploads/2023/03/co2-technical-brief-ochmo.pdf",
    ),
    SourceLink(title="NASA ECLSS brief", url=f"{_NASA}/2023/12/ochmo-tb-002-eclss.pdf"),
    SourceLink(title="CSA Radi-N2", url="https://www.asc-csa.gc.ca/eng/sciences/radi-n2.asp"),
    SourceLink(
        title="CSA Space Health / Bio-Monitor", url="https://hdiac.dtic.mil/articles/peak-performance-in-microgravity"
    ),
    SourceLink(
        title="Three-Item Loneliness Scale",
        url="https://www.phenxtoolkit.org/toolkit_content/supplemental_info/psychosocial/measures/Social_Isolation.doc",
    ),
    SourceLink(title="PVT-B validation", url="https://pmc.ncbi.nlm.nih.gov/articles/PMC3197786"),
    SourceLink(title="3-minute PVT lapse bands", url="https://pmc.ncbi.nlm.nih.gov/articles/PMC3190077"),
    SourceLink(
        title="Subjective vs objective gap (NASA JSC)",
        url="https://www.24-7pressrelease.com/press-release/414258/clearing-the-space-fog",
    ),
    SourceLink(title="AURORA (main rival)", url="https://github.com/fabriciojunio/aurora-astronaut-health"),
)
