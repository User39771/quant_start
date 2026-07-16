# 000063 Endpoint Forensics v1.5

## Conclusion

`confirmed_suspension`

ZTE Corporation (`000063`) did not trade on 2021-03-31. The missing price is a real suspension endpoint, not a confirmed source gap. No price is imputed, forward-filled, backfilled, or replaced with the 2021-04-01 price.

## Evidence

1. **Official disclosure:** CNInfo announcement `1209484316`, published 2021-03-31, is titled *关于中国证监会上市公司并购重组审核委员会审核公司发行股份购买资产并募集配套资金事项的A股股票停牌公告*. This directly records the A-share suspension.  
   Source: https://static.cninfo.com.cn/finalpage/2021-03-31/1209484316.PDF
2. **Eastmoney historical kline:** the independent endpoint returns observations for 2021-03-30 and 2021-04-01, with no 2021-03-31 row.  
   Source: https://push2his.eastmoney.com/api/qt/stock/kline/get?secid=0.000063&klt=101&fqt=1&beg=20210325&end=20210405&fields1=f1,f2,f3&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61
3. **Tencent historical qfq kline:** independently shows the same 2021-03-30 to 2021-04-01 gap.  
   Source: https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=sz000063,day,2021-03-25,2021-04-05,20,qfq

## Endpoint Treatment

- 2021-03-31 remains missing for `000063`.
- When it is a rebalance start endpoint, `000063` is `start_ineligible` for that period.
- Its absence must not change the frozen period grid.
- This finding does not establish a general suspension-aware portfolio accounting rule for expanded-history replay.
