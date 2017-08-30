# rov-measurement-code

## Active Experiments:

## Prefer non-invalid: Experiment 7
This experiment involves two prefixes, a reference prefix and an experiment prefix. The objective is to test whether there are BGP routers that will prefer a valid route to a more attractive invalid route.
To test this, we announce the prefixes using two different origin AS, to create competing announcements.
For technical reasons we cannot send out these competing announcements from the same mux, so we are going to use the amsterdam01 (origin AS X henceforth) and seattle01 (origin AS Y henceforth) muxes since they provide the best connectivity.

We authorize both ASX and ASY to announce the reference prefix and statically announce the prefix from both muxes.
We authorize only one AS, say ASX, to announce the experiment prefix but still statically announce the experiment prefix from both muxes. This leads to the announcement from ASX being valid and the one from ASY being invalid.

If we observe a BGP router that for the reference prefix chooses the route with origin ASY, but for the experiment prefix chooses the route with origin ASX, this is a strong indicator that the router prefers non-invalid to invalid routes.

We flip the ROA for the experiment prefix periodically, making ASXes announcement invalid and ASY in turn invalid. This way we can test routers that have chosen the route with origin ASX for the reference prefix.

---------

BGP Announcements (static, no withdraws): 

| Prefix | Mux | Origin AS |
|--------|-----|-----------|
|147.28.254.0/24|amsterdam01|61575|
|147.28.255.0/24|seattle01|61576|

ROAs:

| Prefix | Mux | OriginAS |RPKI validity state |
|--------|-----|----------|---------------------|
| 147.28.254.0/24 | amsterdam01 | 61575 | always VALID |
| 147.28.254.0/24 | seattle01 | 61576 | always VALID|
| 147.28.255.0/24 | amsterdam01 | 61575 | INVALID between 00:30 UTC and 08:30, else VALID |
| 147.28.255.0/24 | seattle01 | 61576 | INVALID between 08:30 UTC and 16:30 UTC, else VALID|

---------

## Clean implementation testing: Experiment 6
This experiment involves two prefixes, a reference prefix and an experiment prefix. The objective is to test whether there are ROV implementations that do not automatically reevaluate an existing route if a ROA changes. To test this, we do not statically announce our prefixes as in Experiment 5, rather we announce them briefly and then withdraw them again. We change the ROA for the experiment prefix while the prefixes are not announced. After ample propagation time, we re-announce (and then withdraw) the prefixes to see whether other routes were chosen. If an AS chooses different routes for the experiment prefix depending on RPKI validity status, and did not do this in Experiment 5, this indicates that this AS is using an implementation that does not properly reevaluate RPKI validity status of existing routes.

| Time (UTC) | Action |
|------------|--------|
| 00:30 | Publish ROA for experiment prefix, making announcements for it **valid** |
| 07:00 | Announce both prefixes. ROA should have propagated by now (6:30 hours of time)|
| 08:00 - 08:10 | Collector dumps happen. Announcements should have propagated by now (1h of time) |
| 08:15 | Withdraw both prefixes |
| 08:30 | Publish ROA for experiment prefix, making announcements for it **invalid**. Withdraws should have propagated by now (15m of time).|
| 15:00 | Announce both prefixes |
| 16:00 - 16:10 | Collector dumps happen. Routes for experiment prefix are **invalid**.|
| 16:15 | Withdraw both prefixes | 
| 23:00 | Announce both prefixes | 
| 00:00 - 00:10 | Collector dumps happen. Routes for experiment prefix are still **invalid**. AS with slow propagation time might show different routes now than at 16:00 dump |
| 00:15 | Withdraw both prefixes |

We are announcing two pairs of reference/experiment prefixes:

| Reference prefix | Experiment prefix | Mux | Announced to |
|------------------|-------------------|-----|--------|
| 147.28.250.0/24 | 147.28.251.0/24 | amsterdam01 | All peers except route servers and AS8283 |
| 147.28.252.0/24 | 147.28.253.0/24 | amsterdam01 | Amsix route servers | 


This experiment was first started on: 2017-07-19

RESTART OF EXPERIMENT DUE TO BUGS: 2017-07-25


## Find AS with policy to *drop* invalid routes: Experiment 5

| Prefix | Announced via | RPKI validity state |
|--------|---------------|---------------------|
| 147.28.240.0/24 | All amsterdam01 peers | always VALID |
| 147.28.241.0/24 | All amsterdam01 peers | INVALID between 04:00 UTC and 12:00 UTC, else VALID|
|---|
| 147.28.242.0/24 | AMSIX Falcon RS (via amsterdam01 mux), ids 102 and 104 | always VALID |
| 147.28.244.0/24 | AMSIX Falcon RS (via amsterdam01 mux), ids 102 and 104 | INVALID between 04:00 UTC and 12:00 UTC, else VALID|
|---|
|147.28.243.0/24| AMSIX Default Routeserver, ids 27 and 29 | always VALID |
|147.28.245.0/24| AMSIX Default Routeserver, ids 27 and 29 | INVALID between 04:00 UTC and 12:00 UTC, else VALID |
|---|
|147.28.246.0/24| All peers except Falcon and Default RS (via amsterdam01 mux) | always VALID |
|147.28.247.0/24| All peers except Falcon and Default RS (via amsterdam01 mux) | INVALID between 04:00 UTC and 12:00 UTC, else VALID|
|---|
|147.28.248.0/24| All peers of seattle01 | always VALID |
|147.28.249.0/24|  All peers of seattle01 | INVALID between 04:00 UTC and 12:00 UTC, else VALID |


---------------


## Data

All data is publicly available via RIPE RIS and RouteViews collectors. We recommend using [bgpstream](https://bgpstream.caida.org/) to obtain it. An overview over our announcement timing can be seen at 
[RIPEstat](https://stat.ripe.net/widget/routing-history#w.resource=147.28.240.0%2F20&w.starttime=2016-05-15T00%3A00%3A00&w.endtime=2017-08-30T00%3A00%3A00).

The 'route_changes_direct' scripts take BGP data as input and will output a number of vantage points that *could* be using ROV to filter. Individual examination is required as of now since one AS filtering invalids might cause other AS with vantage points to seem like they are filtering as well.
