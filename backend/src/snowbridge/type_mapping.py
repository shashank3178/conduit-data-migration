"""Conservative cross-engine type mapping; unsafe conversions are explicit."""
from __future__ import annotations
import re
from snowbridge.contracts import MappingSafety, TypeMapping
_ALIASES={"postgres":"postgresql","postgresql":"postgresql","mysql":"mysql","mariadb":"mysql","oracle":"oracle"}
def normalize_engine(engine:str)->str:
    try:return _ALIASES[engine.strip().lower()]
    except KeyError as exc:raise ValueError(f"unsupported database engine: {engine!r}") from exc

def map_type(source_engine:str,target_engine:str,native_type:str,precision:int|None=None,
             scale:int|None=None,length:int|None=None,timezone_aware:bool|None=None)->TypeMapping:
    src,dst=normalize_engine(source_engine),normalize_engine(target_engine)
    raw=" ".join(native_type.strip().lower().split())
    \n    modifier=re.search(r"\((\d+)(?:,\s*(\d+))?\)",raw)\n    if modifier:\n        if precision is None: precision=int(modifier.group(1))\n        if scale is None and modifier.group(2) is not None: scale=int(modifier.group(2))\n        if length is None and modifier.group(2) is None and any(t in raw for t in ("char","varchar","bit")): length=int(modifier.group(1))\n    base=re.sub(r"\(\d+(?:,\s*\d+)?\)","",raw).strip()
    unsigned="unsigned" in raw
    base=re.sub(r"\s+unsigned$","",base)
    if src==dst:return TypeMapping(native_type,native_type,MappingSafety.AUTOMATIC,"Preserve same-engine native type.")
    target=None; safety=MappingSafety.AUTOMATIC; reason=""
    if base in {"tinyint","smallint","int","integer","serial","smallserial"}:
        target="smallint" if base in {"tinyint","smallint","smallserial"} else "integer"
        if base=="tinyint" and (length==1 or re.search(r"\\(1\\)",raw)): target="boolean"; reason="MySQL TINYINT(1) is conventionally boolean; verify source values."
        if unsigned and base in {"tinyint","smallint","int","integer"}:
            target={"tinyint":"smallint","smallint":"integer","int":"bigint","integer":"bigint"}[base]
            safety=MappingSafety.WARNING; reason="Unsigned source range requires validation against the wider target type."
    elif base in {"mediumint","bigint","bigserial"}: target="bigint"
    elif base in {"number","numeric","decimal","dec"}:
        target=f"numeric({precision},{scale})" if precision is not None and scale is not None else "numeric"
        if src=="oracle" and precision is None:
            safety=MappingSafety.WARNING; reason="Unconstrained Oracle NUMBER requires value-range profiling."
    elif base in {"float","real","double","double precision","binary_float","binary_double"}:
        target="real" if base in {"float","real","binary_float"} else "double precision"
    elif base in {"bool","boolean"}: target="boolean"
    elif base=="bit": target="boolean" if length in (None,1) else "bit varying"
    elif base in {"varchar","varchar2","nvarchar2","character varying","char","nchar","character"}:
        target=f"varchar({length})" if length else "text"
    elif base in {"text","tinytext","mediumtext","longtext","clob","nclob"}:
        target="text"
        if base in {"clob","nclob","longtext"}:safety=MappingSafety.WARNING;reason="Large-object streaming and character-set semantics require validation."
    elif base in {"blob","tinyblob","mediumblob","longblob","bytea","raw","long raw","bfile"}:
        target="bytea"
        if base=="bfile":safety=MappingSafety.REQUIRES_TRANSFORM;reason="Oracle BFILE is an external locator, not inline binary data."
        elif base in {"long raw","longblob"}:safety=MappingSafety.WARNING;reason="Large binary values require streaming and size validation."
    elif base=="date":
        target="timestamp" if src=="oracle" else "date"
        if src=="oracle":safety=MappingSafety.WARNING;reason="Oracle DATE includes time-of-day; timestamp avoids truncation."
    elif base in {"timestamp","datetime","timestamp without time zone"}:target="timestamp"
    elif base in {"timestamptz","timestamp with time zone","timestamp with local time zone"}:
        target="timestamp with time zone"
        if base=="timestamp with local time zone":safety=MappingSafety.WARNING;reason="Oracle session time-zone normalization must be explicit."
    elif base in {"json","jsonb"}:target="jsonb"
    elif base in {"uuid","uniqueidentifier"}:target="uuid"
    elif base in {"enum","set"}:target="text";safety=MappingSafety.WARNING;reason="Preserve enumerated values and domain constraints separately."
    elif base in {"geometry","geography","sdo_geometry"}:safety=MappingSafety.REQUIRES_TRANSFORM;reason="Spatial reference and geometry semantics need an explicit transform."
    elif base=="xml":target="xml"
    elif base=="year":target="smallint"
    else:safety=MappingSafety.UNSUPPORTED;reason="No safe automatic mapping is registered for this native type."
    if target is None and safety is not MappingSafety.UNSUPPORTED:safety=MappingSafety.UNSUPPORTED
    return TypeMapping(native_type,target or "",safety,reason or f"Mapped {src} {native_type} to {dst} {target}.")
