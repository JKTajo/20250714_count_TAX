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

    temp_df = df.copy()
    
    # 기초 전처리: 날짜 및 사업자번호 문자열화
    temp_df['Date'] = pd.to_datetime(temp_df['Date']).dt.strftime('%Y%m%d')
    temp_df['day'] = temp_df['Date'].str[-2:]
    temp_df['TaxNo_Send'] = temp_df['TaxNo_Send'].astype(str).str.replace('-', '')
    temp_df['TaxNo_get'] = temp_df['TaxNo_get'].astype(str).str.replace('-', '')
    
    # 홈택스 표준 컬럼 정의 (공통 키)
    key_id = ['Date', 'TaxNo_Send', 'J1', 'Title_send', 'Name_send',
              'Addr_send', 'sub1', 'sub2', 'Email_send',
              'TaxNo_get', 'J2', 'TaxTitle_get', 'Name_get',
              'Addr_get', 'type1', 'type2', 'Email_get', 'Email2_get', 'note_Sum']

    # 공급가액 0원 초과 데이터만 필터링
    temp_df = temp_df[temp_df['price'] > 0]

    if is_free_tax:
        # --- [면세: 수도료 전용 로직] ---
        merged_df = temp_df[temp_df['item'] == '수도료'].copy()
        if merged_df.empty: return pd.DataFrame()
        
        merged_df['code'] = '02'
        merged_df['price_sum'] = merged_df['price'].fillna(0).astype(int)
        merged_df['VAT_sum'] = 0
        merged_df['day_1'] = merged_df['day']
        merged_df['item_1'] = merged_df['item']
        merged_df['price_1'] = merged_df['price']
        merged_df['VAT_1'] = 0
    else:
        # --- [과세: 임대료/관리비/전기료/주차료 병합 로직] ---
        # 특정 업체(하나은행 등) 처리 및 품목별 분리
        df_Hana = temp_df[temp_df['TaxNo_get'].str.contains('2298500670', na=False)]
        df_others = temp_df[~temp_df['TaxNo_get'].str.contains('2298500670', na=False)]

        df1 = pd.concat([df_Hana, df_others[df_others['item'] == '임대료']])
        df2 = df_others[df_others['item'] == '관리비']
        df3 = df_others[df_others['item'] == '전기료']
        df4 = df_others[df_others['item'] == '주차료']
        
        if df1.empty and df2.empty and df3.empty and df4.empty: return pd.DataFrame()

        # 다중 품목 병합 (Outer Join)
        merged_df = pd.merge(df1, df2, how='outer', on=key_id, suffixes=('_1', '_2'))
        merged_df = pd.merge(merged_df, df3, how='outer', on=key_id)
        merged_df = pd.merge(merged_df, df4, how='outer', on=key_id, suffixes=('_3', '_4'))
        
        merged_df['code'] = '01'
        price_cols = ['price_1', 'price_2', 'price_3', 'price_4']
        vat_cols = ['VAT_1', 'VAT_2', 'VAT_3', 'VAT_4']
        
        for col in price_cols + vat_cols:
            if col not in merged_df.columns: merged_df[col] = 0

        merged_df['price_sum'] = merged_df[price_cols].fillna(0).sum(axis=1).astype(int)
        merged_df['VAT_sum'] = merged_df[vat_cols].fillna(0).sum(axis=1).astype(int)

    # 최종 홈택스 양식 컬럼 정렬
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
    
    # 누락된 컬럼 빈값으로 생성 및 정리
    for col in final_columns:
        if col not in merged_df.columns: merged_df[col] = ''
            
    df_final = merged_df[final_columns].copy()
    df_final["etc5"] = "02" # 전자발행 구분
    
    return df_final.fillna('')

# --- 2. Streamlit UI 부분 ---
st.set_page_config(page_title="홈택스 통합 변환기", layout="wide")

st.title("📄 이카운트 → 홈택스 통합 변환기")
st.markdown("""
이 도구는 이카운트 엑셀 데이터를 **홈택스 일괄 업로드 양식**으로 변환합니다.  
업로드 후 **[변환 실행]** 버튼을 누르면 과세와 면세 파일이 각각 생성됩니다.
""")

uploaded_file = st.file_uploader("📂 이카운트 엑셀 파일(.xlsx)을 선택하세요", type=["xlsx"])

if uploaded_file:
    try:
        # 데이터 로드 (첫 1행 건너뜀, 하단 합계 제외)
        df_original = pd.read_excel(uploaded_file, skiprows=1, skipfooter=2, header=0)
        
        with st.expander("🔍 업로드 데이터 미리보기"):
            st.dataframe(df_original, use_container_width=True)

        st.divider()

        # --- 변환 실행 버튼 ---
        if st.button("🚀 홈택스 양식으로 변환 실행", use_container_width=True, type="primary"):
            with st.spinner('데이터를 분류하고 엑셀 파일을 생성 중입니다...'):
                
                # 1. 데이터 변환 로직 가동
                tax_df = process_ecount_file(df_original.copy(), is_free_tax=False)
                free_df = process_ecount_file(df_original.copy(), is_free_tax=True)

                # 2. 화면 레이아웃 구성
                col1, col2 = st.columns(2)

                # --- 왼쪽: 과세 세금계산서 ---
                with col1:
                    st.subheader("1️⃣ 과세 세금계산서")
                    if not tax_df.empty:
                        st.info(f"임대료, 관리비 등 총 {len(tax_df)}건")
                        
                        # 엑셀 파일 생성
                        tax_buffer = io.BytesIO()
                        with pd.ExcelWriter(tax_buffer, engine='openpyxl') as writer:
                            tax_df.to_excel(writer, sheet_name='sale1', index=False, startrow=5)
                        
                        st.download_button(
                            label="📥 과세 파일 다운로드 (tax_upload.xlsx)",
                            data=tax_buffer.getvalue(),
                            file_name="tax_upload.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            use_container_width=True
                        )
                        st.dataframe(tax_df, height=400)
                    else:
                        st.warning("변환할 과세 데이터가 없습니다.")

                # --- 오른쪽: 면세 일반계산서 ---
                with col2:
                    st.subheader("2️⃣ 면세 일반계산서")
                    if not free_df.empty:
                        st.info(f"수도료 전용 총 {len(free_df)}건")
                        
                        # 엑셀 파일 생성
                        free_buffer = io.BytesIO()
                        with pd.ExcelWriter(free_buffer, engine='openpyxl') as writer:
                            free_df.to_excel(writer, sheet_name='free_sale', index=False, startrow=5)
                        
                        st.download_button(
                            label="📥 면세 파일 다운로드 (freetax_upload.xlsx)",
                            data=free_buffer.getvalue(),
                            file_name="freetax_upload.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            use_container_width=True
                        )
                        st.dataframe(free_df, height=400)
                    else:
                        st.warning("변환할 면세(수도료) 데이터가 없습니다.")

    except Exception as e:
        st.error(f"❌ 변환 중 오류가 발생했습니다. 파일 형식을 확인해주세요.\n(에러 내용: {e})")
