# IfcVirtualGridIntersection

_IfcVirtualGridIntersection_ defines the derived location of the intersection between two grid axes. Offset values may be given to set an offset distance to the grid axis for the calculation of the virtual grid intersection.

The two intersecting axes (_IntersectingAxes_) define the intersection point, which exact location (in terms of the Cartesian point representing the intersection) has to be calculated from the geometric representation of the two participating curves.

> NOTE&nbsp; The _IfcGrid_ local placement, that can be provided relative to the local placement of another spatial structure element, has to be taken into account for calculating the absolute placement of the _IfcVirtualGridIntersection_. Where rules and informal rules ensure, that the _IntersectingAxes_ belong to the same _IfcGrid_

Offset values may be given (_OffsetDistances_). If given, the position within the list of _OffsetDistances_ corresponds with the position within the list of _IntersectingAxes_. Therefore:

* _OffsetDistances[1]_ sets the offset to _IntersectingAxes[1]_,
* _OffsetDistances[2]_ sets the offset to _IntersectingAxes[2]_, and
* _OffsetDistances[3]_ sets the offset to the virtual intersection in direction of the orientation of the cross product of _IntersectingAxes[1]_ and the orthogonal complement of the _IntersectingAxes[1]_ (which is the positive or negative direction of the z axis of the design grid position).

The following figures/ explain the usage of the _OffsetDistances_ and _IntersectingAxes_ attributes.

<table cellpadding="2" cellspacing="2">
<tr valign="top"><td align="left" valign="top"><img src="../../../../figures/ifcvirtualgridintersection-layout1.gif" alt="2D offsets" border="0" height="300" width="400"></td>
<td style="vertical-align:bottom">
<p class="small">Figure 1 illustrates two offset distances given where the virtual intersection is defined in the xy plane of the grid axis placement.</p>
</td>
</tr>
<tr><td><p class="figure">Figure 1 &mdash; Virtual grid intersection with two offsets</p></td>
<td>&nbsp;</td></tr>
</table>

<table cellpadding="2" cellspacing="2"><tr valign="top"><td align="left" valign="top"><img src="../../../../figures/ifcvirtualgridintersection-layout2.gif" alt="3D offsets" border="0" height="300" width="400"></td>
<td style="vertical-align:bottom">
<p class="small">Figure 2 illustrates three offset distances given where the virtual intersection is defined by an offset (in direction of the
z-axis of the design grid placement) to the virtual intersection in the xy plane of the grid axis placement.</p>
</td>
</tr>
<tr><td><p class="figure">Figure 2 &mdash; Virtual grid intersection with three offsets</p></td>
<td>&nbsp;</td></tr>
</table>

The distance of the offset curve (_OffsetDistances[n]_) is measured from the basis curve. The distance may be positive, negative or zero. A positive value of distance defines an offset in the direction which is normal to the curve in the sense of an anti-clockwise rotation through 90 degrees from the tangent vector T at the given point. (This is in the direction of orthogonal complement(T).) This can be reverted by the _SameSense_ attribute at _IfcGridAxis_ which may switch the sense of the _AxisCurve_.

<table cellpadding="2" cellspacing="2">
<tr><td align="left" valign="top" width="400"><img src="../../../../figures/ifcvirtualgridintersection-offset1.gif" alt="offset direction" border="0" height="211" width="306"></td>
<td style="vertical-align:bottom">
<p class="small">Figure 3 illustrates an example of a negative offset where the figure shows the side of the offset.</p>
<ul>
<li class="small"><em>IntersectingAxes[1].AxisCurve</em> is an
<em>IfcTrimmedCurve</em> with an <em>IfcCircle</em> as
<em>BasisCurve</em> and <em>SenseAgreement</em> = TRUE.</li>
<li class="small"><em>IntersectingAxes[1].SameSense</em> = TRUE.</li>
<li class="small"><em>OffsetDistances[1]</em> is a negative length measure</li>
</ul>
</td>
</tr>
<tr><td><p class="figure">Figure 3 &mdash; Virtual grid intersection negative offset</p></td>
<td>&nbsp;</td></tr>
</table>

> HISTORY&nbsp; New entity in IFC1.5.

{ .change-ifc2x}
> IFC2x CHANGE&nbsp; Renamed from IfcConstraintRelIntersection.

{ .spec-head}
Informal Propositions:

1. Both, _IntersectingAxes[1]_ and _IntersectingAxes[2]_ shall be two _IfcGridAxis_ defined by the same _IfcGrid_.
2. _IntersectingAxes[1]_ and _IntersectingAxes[2]_ shall not be part of the same row of grid axes, i.e. both shall not be within the same set of _IfcGrid.UAxes_ or _IfcGrid.VAxes_ of the corresponding _IfcGrid_.

## Attributes

### IntersectingAxes
Two grid axes which intersects at exactly one intersection (see also informal proposition at IfcGrid). If attribute OffsetDistances is omitted, the intersection defines the placement or ref direction of a grid placement directly. If OffsetDistances are given, the intersection is defined by the offset curves to the grid axes.

### OffsetDistances
Offset distances to the grid axes. If given, it defines virtual offset curves to the grid axes. The intersection of the offset curves specify the virtual grid intersection.
