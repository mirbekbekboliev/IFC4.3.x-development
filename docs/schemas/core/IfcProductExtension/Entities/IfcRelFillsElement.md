# IfcRelFillsElement

_IfcRelFillsElement_ is an objectified relationship between an opening element and an element that fills (or partially fills) the opening element. It is an one-to-one relationship.

> NOTE&nbsp; View definitions or implementer agreements may restrict an opening to be filled by one filling element only.

As shown in Figure 1, the insertion of a door into a wall is represented by two separate relationships. First the door opening is created within the wall by _IfcWall(StandardCase) <-- IfcRelVoidsElement --> IfcOpeningElement_, then the door is inserted within the opening by _IfcOpeningElement <-- IfcRelFillsElement --> IfcDoor_.

&nbsp;

!["relationships for filling"](../../../../figures/ifcrelfillselements-fig1.png "Figure 1 &mdash; Relationships for element filling")

> HISTORY&nbsp; New entity in IFC1.0

## Attributes

### RelatingOpeningElement
Opening Element being filled by virtue of this relationship.

### RelatedBuildingElement
Reference to ~~building~~ element that occupies fully or partially the associated opening.
{ .change-ifc2x}
> IFC2x CHANGE&nbsp; The data type has been changed from _IfcBuildingElement_ to _IfcElement_ with upward compatibility for file based exchange.
