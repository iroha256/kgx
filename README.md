# kgx
2022/04/08付でフォーク元リポジトリより、本リポジトリへ移行しました。

<br>Postgre SQL 12.3によりデータベースの管理がされています。

# 各種DBのテーブル、カラムについて
> auction
>
>> ch_id: チャンネルID格納. bigint. unique key<br>
>> auction_owner_id: そのチャンネルにおけるオークションのオーナーのid. bigint<br>
>> embed_message_id: オークション情報が載ってるembedのmessage_id: bigint<br>
>> auction_item: そのチャンネルの出品物. text<br>
>> auction_start_price: text<br>
>> auction_bin_price: text<br>
>> auction_end_time: 終了時刻がdatetime型で入る。 text <br>
>> unit: 単位. text<br>
>> notice: 特記事項. text<br>
>> before_auction: 前回開催されたオークションのid。auction_back用。int<br> 
>
> deal
>
>> ch_id: チャンネルID格納. bigint. unique key<br>
>> deal_owner_id: そのチャンネルにおけるオークションのオーナーのid. bigint<br>
>> embed_message_id: オークション情報が載ってるembedのmessage_id: bigint<br>
>> deal_item: そのチャンネルの出品物. text<br>
>> deal_hope_price: text<br>
>> deal_end_time: 終了時刻がdatetime型で入る。 text <br>
>> unit: 単位. text<br>
>> notice: 特記事項. text<br>
>
> bid_ranking
>
>> bidder_name: 落札者の名前 text<br>
>> item_name: 出品物の名前 text<br>
>> bid_price 落札額 smallint<br>
>> seller_id: ※ idと言っておきながら格納されているのはニックネーム。seller_nameにするべき text<br>
>
> user_data
>
>> user_id: 参加時のmcid認証が通ると登録される。 bigint unique key<br>
>> bid_score: 落札ポイントを格納。 smallint(3万以上とか考慮してない)<br>
>> warn_level: 警告レベルを格納。 smallint(0-3以外を取らない変数のため要求を満たす)<br>
>> uuid: ハイフンなしのMinecraftのuuid。 text[]<br>
>> dm_flag: DMができるかのフラグを格納。 boolean<br>
>
> tend
>
>> ch_id: チャンネルID格納. bigint. unique key<br>
>> tender_id: 入札した人のidを格納。時系列で配列になっている。 bigint[]. <br>
>> tend_price: 入札額を格納。stack_check関数を通すこと。時系列で配列になっている。 integer[]. <br>
>
> auction_info
>
>> id: オークション毎に生成される一意のid。serial primary key<br>
>> ch_id: オークションが開催されたチャンネルのid。bigint<br>
>> owner_id: オークション開催者のid。bigint<br>
>> item: 出品物。text<br>
>> start_price: 開始価格。int<br>
>> bin_price: 即決価格。なしの場合はnull。int<br>
>> end_time: 終了時刻。timestamp<br>
>> unit: オークションの単位。text<br>
>> notice: 特記事項。text<br>
>> tend: 入札履歴[入札者, 入札額]の配列。integer[][2]<br>
>> embed_id: オークション情報が載ってるembedのmessage_id。bigint<br>

# コミットルール
始めに英単語1字を付与すること。[ADD] [CHANGE] [DELETE] [Refactor] ここら辺をよく使うかな

# git変更について
ここにマージされたものはそのまま本番環境にリリースされます。そのため、機能単位の変更を入れる場合は!versionの数値を挙げてください。
その際のコミット名は[UPDATE]を付与してください。

# コマンド、変数の命名規則
snake_caseで記載してください。

# メモ
2021/03/27　Deploy v1000を達成
