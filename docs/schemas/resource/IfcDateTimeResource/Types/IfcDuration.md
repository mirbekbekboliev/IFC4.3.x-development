# IfcDuration

The _IfcDuration_ identifies a quantity of time (or a "length" of an event occurring in time).

This lexical representation for _IfcDataTime_ is PnYnMnDTnHnMnS, where nY represents the number of years, nM the number of months, nD the number of days, 'T' is the date/time separator, nH the number of hours, nM the number of minutes and nS the number of seconds. The number of seconds can include decimal digits to arbitrary precision.

> EXAMPLE&nbsp; P2Y10M15DT10H30M20S (duration of two years, 10 months, 15 days, 10 hours, 30 minutes and 20 seconds).

> NOTE&nbsp; See extended format representation of **duration** as defined in ISO&nbsp;8601. The restrictions defined in XML Schema Part 2 apply.

> HISTORY&nbsp; New type in IFC4
