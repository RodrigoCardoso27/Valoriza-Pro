st.title("⚽ Valoriza Pro - O Oráculo")
st.write("Deixe a inteligência artificial analisar os dados e escalar seu time.")

orcamento_usuario = st.number_input("Qual o seu patrimônio atual (C$)?", value=100.0)

# O único botão do site
if st.button("🪄 Gerar Time Perfeito da Rodada", type="primary", use_container_width=True):
    with st.spinner("Analisando scouts da última rodada, cruzando confrontos e calculando valorização..."):
        
        # Aqui entra o seu "Motor Python" pesado
        time_gerado = motor_de_analise_profunda(orcamento_usuario)
        
        # Depois que o motor pensa, a gente exibe o campo verde
        renderizar_campo_com_time(time_gerado)
        
        st.success("Time gerado com sucesso!")
