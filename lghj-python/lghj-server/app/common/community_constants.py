"""社区模块（博客/评论/关注）常量。

对应复现原 Java：
- feng-lghj/lghj-server/src/main/java/com/lghj/constant/RedisConstant.java（社区相关键）
- feng-lghj/lghj-server/src/main/java/com/lghj/constant/LikeStatusConstant.java

说明：原 RedisConstant 为单一常量类；任务A 已将股票相关键写入
app/common/constants.py，本文件补充社区模块（Phase 3）用到的键，
键名逐字照抄原 Java，**禁止改动**。
"""

from __future__ import annotations

# ====================== RedisConstant.java（社区部分） ======================
# 关注的用户Key前缀
FOLLOWS_KEY = "follows:"
# 博客点赞Key前缀：blog:liked:{blogId}（ZSet，member=用户id，score=点赞时间戳毫秒）
BLOG_LIKED_KEY = "blog:liked:"
# 关注的博主的博客Key前缀：feed:{userId}（ZSet，member=博客id，score=发布时间戳毫秒）
FEED_KEY = "feed:"
# 博客评论点赞Key前缀：blog:comment:liked:{commentId}（Set，member=用户id）
BLOG_COMMENT_LIKED_KEY = "blog:comment:liked:"

# ====================== LikeStatusConstant.java ======================
# 点赞状态-已点赞
LIKED_STATUS = 1
# 点赞状态-未点赞
UNLIKED_STATUS = 0
