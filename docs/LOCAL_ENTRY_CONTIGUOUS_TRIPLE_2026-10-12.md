# 第二十二层：天赋入口连续三帧观察

独立覆盖固定对应源码完整1..21之后的天赋入口调度；旧补丁/冻结source/unknown记录不改，不加入通用库存、升级、转化或确认消费。

原接口返回字段保留，新增 `talentEntryObservationMethod=bounded_contiguous_entry_triple`、`talentEntryObservationLimitMs=12000`、`talentEntryObservationPollMs=300`。原一次天赋导航后，在同一12秒/最多41次观察窗口中按300ms有界读取。`rawFrames`保留包括坏third的完整顺序；只在首次连续三张a/b/c同时满足原PairFailure(a,b)及ClickBound(b,c)时，设置twoPickedEntryFrames=[a,b]/entryClickFrame=c，并使用c同一当前图像的坐标点击一次。第三张坏时继续窗口，只推进最近连续帧，不选择不连续旧pair，不再多取第四张，也不重发导航。

每帧新增 `readCompletedAt` 为全部OCR及私有PNG诊断完成的真实读结束时间；原 `observedAt` 不变，不冒称新的采集时间或后端sequence。判据的now明确用c.readCompletedAt，原1500ms/5000ms与全header/Menu/3Lvl、四边2px及6px完整规则不降。prompt/focus/revive变化仍立即停止，deadline原样，失败原文/原PNG保留，不伪造成功。

Release x64零错误，127项限定纯回归全部通过。最后补明确读完成时间字段后，32项入口/header限定回归再次通过；新增6例涵盖坏third保留、后续首个连续三张、页头/弹窗/失焦/复活、位置及重复/过期时间拒绝。该纯验证不等于新鲜实机预览成功，真实22只读检查仍待独立scope。

部署仅替换顶层引擎文件；235份当前User文件逐个SHA完全一致。DLL22：`DCADAE994BC75EEB3D246EA2BE99AD0C57B3F6C571CC31B1DD7302E2DEE9103D`；补丁22：`D2A5A847B8B23BD701AC91B4B301662A391526A0EF3559D4A95ED278F5EB1C59`。真正isolated固定基线1..21后22forward及主源reverse检查通过；旧DLL21与新DLL/完整对应源/序列只在本机冻结，历史补丁字节不改。
