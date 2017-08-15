Replication of the methodology described in 'Are We There Yet? On RPKI's Deployment and Security' paper
published at NDSS'17[https://www.internetsociety.org/sites/default/files/ndss2017\_06A-3\_Gilad\_paper.pdf].


uncontrolled-rov-classification.py requires these arguments:
path\_diversity : CSV file obtained by running path-diversity.py with **the same BGP RIB data that will be used for this script**
as\_relationship : CAIDAs  AS relationship files found [here](http://data.caida.org/datasets/as-relationships/serial-1/)
data : BGP RIB data annotated with RPKI information. Format is that of [bgpreader](https://bgpstream.caida.org/docs/tools/bgpreader)
with an added field at the end that is a number between 0 and 5:

```
0: Route is valid
1: Route is unknown
2: Route is invalid
3: Route is invalid because of wrong ASN
4: Route is invalid because of wrong length
5: Route is invalid because of wrong ASN and wrong length
```


Data used in our replication:

BGP RIB Dump (annotated):
ftp://ftp.mi.fu-berlin.de/pub/reuter/ris\_rv\_20161025.1600

CAIDA AS relationship data used:
ftp://ftp.mi.fu-berlin.de/pub/reuter/20161001.as-rel.txt


So overall usage:

./path-diversity <bgp_data>  //outputs path_diversity.csv
./uncontrolled-rov-classification.py path_diversity.csv <bgp_data> <number of random vantage point sets to run analysis with>


Outputs:
All results are in: 'results/analysis_results.txt'
Format:
<number of vantage points>|<number of non-rov AS>|<number of rov candidates>|<number of rov enforcers>|<number of false positive rov candidates>|<number of false positive rov enforcers>
