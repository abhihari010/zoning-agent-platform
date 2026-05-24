__all__ = [
    "AddressTool",
    "CitationTool",
    "ComplianceTool",
    "ComplianceToolResult",
    "IntakeTool",
    "JurisdictionTool",
    "ParcelTool",
    "ReportTool",
]


def __getattr__(name: str):
    if name == "AddressTool":
        from app.tools.address_tool import AddressTool

        return AddressTool
    if name == "CitationTool":
        from app.tools.citation_tool import CitationTool

        return CitationTool
    if name in {"ComplianceTool", "ComplianceToolResult"}:
        from app.tools.compliance_tool import ComplianceTool, ComplianceToolResult

        return {"ComplianceTool": ComplianceTool, "ComplianceToolResult": ComplianceToolResult}[name]
    if name == "IntakeTool":
        from app.tools.intake_tool import IntakeTool

        return IntakeTool
    if name == "JurisdictionTool":
        from app.tools.jurisdiction_tool import JurisdictionTool

        return JurisdictionTool
    if name == "ParcelTool":
        from app.tools.parcel_tool import ParcelTool

        return ParcelTool
    if name == "ReportTool":
        from app.tools.report_tool import ReportTool

        return ReportTool
    raise AttributeError(name)
