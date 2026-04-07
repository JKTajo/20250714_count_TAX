
import streamlit as st
import pandas as pd
import io

# --- 1. 데이터 변환 핵심 로직 함수 ---
def process_ecount_file(df: pd.DataFrame, is_free_tax: bool = False) -> pd.DataFrame:
    """
    이카운트 데이터를 홈택스 과세/면세 양식으로 변환합니다.
    """
    if df.empty:
        return pd.DataFrame()

    # 기초 전처리
    temp_df = df.copy()
    temp_df['code'] = '02' if is_free_tax else '01'
    temp_df['Date'] = temp_df['Date'].astype(str).str[:8]
    temp_df['day'] = temp_df['Date'].str[-2:]
    temp_df['TaxNo_Send'] = temp_df['TaxNo_Send'].astype(str)
    temp_df['TaxNo_get'] = temp_df['TaxNo_get'].astype(str)

    # 공급가액이 0보다 큰 데이터만 필터링
    temp_df = temp_df[temp_df['price'] > 0]

    # 홈택스 표준 컬럼 정의
    key_id = ['code', 'Date', 'TaxNo_Send', 'J1', 'Title_send', 'Name_send',
              'Addr_send', 'sub1', 'sub2', 'Email_send',
              'TaxNo_get', 'J2', 'TaxTitle_get', 'Name_get',
              'Addr_get', 'type1', 'type2', 'Email_get', 'Email2_get', 'note_Sum']

    if is_free_tax:
        # --- [면세: 수도료 전용 로직] ---
        merged_df = temp_df[temp_df['item'] == '수도료'].copy()
        if merged_df.empty: return pd.DataFrame() # 데이터 없으면 빈 프레임 반환
        
        merged_df['price_sum'] = merged_df['price'].fillna(0).astype(int)
        merged_df['VAT_sum'] = 0
        merged_df['day_1'] = merged_df['day']
        merged_df['item_1'] = merged_df['item']
        merged_df['price_1'] = merged_df['price']
        merged_df['VAT_1'] = 0
    else:
        # --- [과세: 임대료/관리비/전기료/주차료 병합 로직] ---
        df_Hana = temp_df[temp_df['TaxNo_get'] == '2298500670']
        df_others = temp_df[temp_df['TaxNo_get'] != '2298500670']

        df1 = df_others[df_others['item'] == '임대료']
        df2 = df_others[df_others['item'] == '관리비']
        df3 = df_others[df_others['item'] == '전기료']
        df4 = df_others[df_others['item'] == '주차료']
        
        if not df_Hana.empty:
            df1 = pd.concat([df_Hana, df1])

        if df1.empty and df2.empty and df3.empty and df4.empty: return pd.DataFrame()

        merged_df = pd.merge(df1, df2, how='outer', on=key_id, suffixes=('_1', '_2'))
        merged_df = pd.merge(merged_df, df3, how='outer', on=key_id)
        merged_df = pd.merge(merged_df, df4, how='outer', on=key_id, suffixes=('_3', '_4'))
        
        price_cols = ['price_1', 'price_2', 'price_3', 'price_4']
        vat_cols = ['VAT_1', 'VAT_2', 'VAT_3', 'VAT_4']
        
        for col in price_cols + vat_cols:
            if col not in merged_df.columns:
                merged_df[col] = 0

        merged_df['price_sum'] = merged_df[price_cols].fillna(0).sum(axis=1).astype(int)
        merged_df['VAT_sum'] = merged_df[vat_cols].fillna(0).sum(axis=1).astype(int)

    # 최종 컬럼 정리
    final_columns = [
        'code', 'Date', 'TaxNo_Send', 'J1', 'Title_send', 'Name_send', 'Addr_send', 
        'sub1', 'sub2', 'Email_send', 'TaxNo_get', 'J2', 'TaxTitle_get', 'Name_get', 
        'Addr_get', 'type1', 'type2', 'Email_get', 'Email2_get', 'price_sum', 
        'VAT_sum', 'note_Sum', 'day_1', 'item_1', 'standard_1', 'quantity_1', 
        'unit_price_1', 'price_1', 'VAT_1', 'note_1', 'day_2', 'item_2', 
        'standard_2', 'quantity_2', 'unit_price_2', 'price_2', 'VAT_2', 'note_2', 
        'day_3', 'item_3', 'standard_3', 'quantity_3', 'unit_price_3', 'price_3', 
        'VAT_3', 'note_3', 'day_4', 'item_4', 'standard_4', 'quantity_4', 
        'unit_price_4', 'price_4', 'VAT_4', 'note_4'
    ]
    
    for col in final_columns:
        if col not in merged_df.columns:
            merged_df[col] = ''
            
    df_final = merged_df[final_columns].copy()
    df_final["etc5"] = "02"
    df_final['TaxNo_get'] = df_final['TaxNo_get'].str.replace('_B', '', regex=False)
    
    return df_final.fillna('')

#비어있는 데이터프레임을 우측에서 땡겨오는 함수정의
def shift_left(df_final):
    #행잡기
    for r in range(df_final.shape[0]):
      #마지막 열제외 열잡기
        for c in range(df_final.shape[1] - 1):
          #0이면 그 뒤에 데이터로 덮고 해당 데이터는 0으로
            if df_final.iloc[r, c] == 0:
                df_final.iloc[r, c] = df_final.iloc[r, c+1]
                df_final.iloc[r, c+1] = 0
#while 문으로 반복하고 break로 탈출
#언제 탈출? 마지막으로 행한 df가 이전 df와 동일할때 탈출
    return df_final

    while True:
        df_prev = df_final.copy()
        shift_left(df_final)
        if df_prev.equals(df_final):
            break
shift_left(df_final)


# --- 2. Streamlit UI 부분 ---
st.set_page_config(page_title="홈택스 통합 변환기", layout="wide")
st.title("📄 이카운트 엑셀 → 홈택스 통합 변환기")
st.info("파일을 업로드하면 [과세 세금계산서]와 [면세 일반계산서] 양식이 자동으로 각각 생성됩니다.")

uploaded_file = st.file_uploader("📂 이카운트 엑셀 파일을 업로드하세요", type=["xlsx", "xls"])

if uploaded_file:
    try:
        df_original = pd.read_excel(uploaded_file, skiprows=1, skipfooter=2, header=0)
        
        with st.expander("📂 원본 데이터 확인"):
            st.dataframe(df_original)

        # 변환 로직 자동 실행 (과세 & 면세)
        tax_df = process_ecount_file(df_original.copy(), is_free_tax=False)
        free_df = process_ecount_file(df_original.copy(), is_free_tax=True)

        # --- 화면 표시: 과세 세금계산서 ---
        st.divider()
        st.subheader("1️⃣ 과세 세금계산서 변환 결과 (임대료, 관리비 등)")
        if not tax_df.empty:
            st.dataframe(tax_df)
            
            output_tax = io.BytesIO()
            with pd.ExcelWriter(output_tax, engine='openpyxl') as writer:
                tax_df.to_excel(writer, sheet_name='sale1', index=False, startrow=5)
            
            st.download_button(
                label="📥 'tax_upload.xlsx' (과세) 다운로드",
                data=output_tax.getvalue(),
                file_name="tax_upload.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
        else:
            st.warning("과세 대상 데이터가 없습니다.")

        # --- 화면 표시: 면세 일반계산서 ---
        st.divider()
        st.subheader("2️⃣ 면세 일반계산서 변환 결과 (수도료 전용)")
        if not free_df.empty:
            st.dataframe(free_df)
            
            output_free = io.BytesIO()
            with pd.ExcelWriter(output_free, engine='openpyxl') as writer:
                free_df.to_excel(writer, sheet_name='free_sale', index=False, startrow=5)
            
            st.download_button(
                label="📥 'freetax_upload.xlsx' (면세) 다운로드",
                data=output_free.getvalue(),
                file_name="freetax_upload.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
        else:
            st.warning("면세 대상(수도료) 데이터가 없습니다.")

    except Exception as e:
        st.error(f"❌ 변환 중 오류 발생: {e}")
