#!/bin/sh
# Per-GPU summary of a dcgmprofrunner thermal_results CSV (1 s samples).
# Usage: sh summarize.sh thermal_results.<host>.1004.900.<date>.csv [dcgmproftester.log]
# Load averages use samples with power >= 150 W: utilization.gpu reads ~70% under
# tensor load, so it is not a usable gate. Slowdown columns count seconds with the
# clocks_event_reasons bit set: 0x20 SW thermal, 0x40 HW slowdown, 0x80 HW power brake.
csv=$1; log=$2
awk -F',' '
function nib(h,  c) { c=index("0123456789abcdef", tolower(h)); return c-1 }
NR>1 {
  i=$7+0; s=$4; gsub(/ /,"",s); ser[i]=s
  c=$8+0; m=$9+0; t=$10+0; p=$11+0; k=$12+0
  r=$13; gsub(/ /,"",r); d=nib(substr(r,length(r)-1,1))
  if (c>maxc[i]) maxc[i]=c; if (m>maxm[i]) maxm[i]=m
  if (!(i in mint) || t<mint[i]) mint[i]=t
  if (p>=150) { n[i]++; sp[i]+=p; sk[i]+=k }
  if (int(d/2)%2) sw[i]++; if (int(d/4)%2) hw[i]++; if (int(d/8)%2) pb[i]++
  if ($17+0>0) { ni++; inlet+=$17 }
}
END {
  printf "GPU  serial          max core  max HBM  min T.limit  load power  load SM clk  HW slowdown  SW slowdown  HW power brake\n"
  for (i=0;i<8;i++) if (i in ser) printf "%-4d %-15s %-9s %-8s %-12s %-11s %-12s %-12s %-12s %s\n", i, ser[i], maxc[i]" C", maxm[i]" C", (mint[i]>=0?"+":"")mint[i], int(sp[i]/(n[i]?n[i]:1))" W", int(sk[i]/(n[i]?n[i]:1))" MHz", hw[i]+0" s", sw[i]+0" s", pb[i]+0" s"
  if (ni) printf "\nInlet temp (in-band ipmitool): mean %.1f C over %d samples\n", inlet/ni, ni
}' "$csv"

# tensor_active_N.results are empty under --no-dcgm-validation; throughput lives in the log.
if [ -n "$log" ]; then
  printf "\n"
  grep -oE 'Worker [0-7]:0 .*\([0-9.]+e\+0[0-9] gflops' "$log" | \
    awk '{sub(/:0/,"",$2); g=$NF; gsub(/[()]/,"",$(NF-1)); s[$2]+=$(NF-1); n[$2]++}
         END {for (i=0;i<8;i++) if (n[i]) printf "GPU %d  mean %.0f TFLOPS over %d samples\n", i, s[i]/n[i]/1000, n[i]}'
fi
