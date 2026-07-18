from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
import pymysql
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime


app = Flask(__name__)
app.secret_key = 'prepaoficial'

# ╔═══════ Conexion a la base de datos ═══════╗
# ╚═══════════════════════════════════════════╝
def conectar_db():
    try:
        conexion = pymysql.connect(
            host='localhost',
            user='root',
            password='',
            db='preparatoria_oficial',
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor
        )
        return conexion
    except Exception as e:
        print("Error al conectar a la base de datos:", e)
        return None


# -----------------------------
# Evitar cache del navegador
# -----------------------------
@app.after_request
def add_header(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


# ╔═══════Login═══════╗
# ╚═══════════════════╝
@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        correo = request.form['usuario'].strip().lower()
        password = request.form['password']
        rol = request.form['rol']

        conexion = conectar_db()
        if not conexion:
            flash("Error al conectar a la base de datos.", "danger")
            return redirect(url_for('login'))

        try:
            with conexion.cursor() as cursor:
                cursor.execute(
                    "SELECT * FROM tbl_usuarios WHERE LOWER(correo_institucional)=%s AND rol=%s",
                    (correo, rol)
                )
                usuario_db = cursor.fetchone()
        finally:
            conexion.close()

        if usuario_db and check_password_hash(usuario_db['password_hash'], password):
            nombre_completo = f"{usuario_db['nombre']} {usuario_db['apellido_paterno']} {usuario_db['apellido_materno']}".strip()
            session['usuario'] = nombre_completo
            session['rol'] = usuario_db['rol']
            session['id_usuario'] = usuario_db['id_usuario']

            flash(f"¡Bienvenido {nombre_completo}!", "success")

            if usuario_db['rol'] == "administrador":
                return redirect(url_for('admin_dashboard'))
            elif usuario_db['rol'] == "docente":
                return redirect(url_for('docente_dashboard'))
            elif usuario_db['rol'] == "orientador":
                return redirect(url_for('panel_orientador'))
        else:
            flash("Correo, contraseña o rol incorrecto.", "danger")
            return redirect(url_for('login'))

    return render_template('login.html')


# ╔═══════ Panel del administrador═══════╗
@app.route('/admin')
def admin_dashboard():
    if 'rol' not in session or session['rol'] != 'administrador':
        flash("Acceso denegado. Solo administradores.", "danger")
        return redirect(url_for('login'))
    conexion = conectar_db()
    data_admin = {}

    if conexion:
        try:
            with conexion.cursor(pymysql.cursors.DictCursor) as cursor:
                # Totales generales
                cursor.execute("SELECT COUNT(*) AS total_estudiantes FROM tbl_estudiantes")
                total_estudiantes = cursor.fetchone()['total_estudiantes']
                cursor.execute("SELECT COUNT(*) AS total_docentes FROM tbl_usuarios WHERE rol = 'docente'")
                total_docentes = cursor.fetchone()['total_docentes']
                cursor.execute("SELECT COUNT(*) AS total_orientadores FROM tbl_usuarios WHERE rol = 'orientador'")
                total_orientadores = cursor.fetchone()['total_orientadores']
                cursor.execute("SELECT COUNT(*) AS total_administradores FROM tbl_usuarios WHERE rol = 'administrador'")
                total_administradores = cursor.fetchone()['total_administradores']
                # Obtener todos los grupos
                cursor.execute("SELECT id_grupo, nombre_grupo FROM tbl_grupos")
                grupos = cursor.fetchall()
                resumen_grupos = []

                for g in grupos:
                    id_grupo = g['id_grupo']

                    # Estudiantes por grupo
                    cursor.execute("""
                        SELECT id_estudiante, nombre, apellido_paterno, apellido_materno 
                        FROM tbl_estudiantes WHERE id_grupo=%s
                    """, (id_grupo,))
                    estudiantes = cursor.fetchall()

                    total_estudiantes_grupo = len(estudiantes)
                    total_rezago = 0
                    total_excelencia = 0

                    for e in estudiantes:
                        estado = calcular_estado_general(cursor, e['id_estudiante'], id_grupo)
                        if estado == "En rezago":
                            total_rezago += 1
                        elif estado == "Excelencia":
                            total_excelencia += 1

                    resumen_grupos.append({
                        "id_grupo": id_grupo,
                        "nombre_grupo": g['nombre_grupo'],
                        "total_estudiantes": total_estudiantes_grupo,
                        "total_rezago": total_rezago,
                        "total_excelencia": total_excelencia
                    })

                data_admin = {
                    'total_estudiantes': total_estudiantes,
                    'total_docentes': total_docentes,
                    'total_orientadores': total_orientadores,
                    'total_administradores': total_administradores,
                    'estudiantes_por_grupo': resumen_grupos
                }

        finally:
            conexion.close()
    return render_template('admin.html', nombre=session.get('usuario'), data=data_admin)



# Listar usuarios por rol
@app.route('/listar_docentes')
def listar_docentes():
    return listar_usuarios_por_rol('docente')

@app.route('/listar_orientadores')
def listar_orientadores():
    return listar_usuarios_por_rol('orientador')

@app.route('/listar_administradores')
def listar_administradores():
    return listar_usuarios_por_rol('administrador')


def listar_usuarios_por_rol(rol):
    conexion = conectar_db()
    usuarios = []
    if conexion:
        try:
            with conexion.cursor() as cursor:
                cursor.execute("""
                    SELECT id_usuario, nombre, apellido_paterno, apellido_materno, 
                           csp, correo_institucional, rol
                    FROM tbl_usuarios
                    WHERE rol = %s
                    ORDER BY nombre ASC
                """, (rol,))
                usuarios = cursor.fetchall()

                # Normalizar visualmente
                for u in usuarios:
                    u['nombre'] = u['nombre'].title()
                    u['apellido_paterno'] = u['apellido_paterno'].title()
                    u['apellido_materno'] = u['apellido_materno'].title()

        finally:
            conexion.close()
    return jsonify(usuarios)

# AGREGAR ASIGNACIÓN 

@app.route('/admin/asignaciones')
def admin_asignaciones():
    conexion = conectar_db()
    with conexion.cursor(pymysql.cursors.DictCursor) as cursor:
        # Usuarios (docentes y orientadores)
        cursor.execute("""
            SELECT id_usuario, CONCAT(nombre, ' ', apellido_paterno, ' ', apellido_materno) AS nombre_completo, rol
            FROM tbl_usuarios
            WHERE rol IN ('docente', 'orientador')
            ORDER BY nombre;
        """)
        usuarios = cursor.fetchall()

        # Materias
        cursor.execute("SELECT id_materia, nombre_materia FROM tbl_materias ORDER BY nombre_materia;")
        materias = cursor.fetchall()

        # Grupos
        cursor.execute("SELECT id_grupo, nombre_grupo FROM tbl_grupos ORDER BY nombre_grupo;")
        grupos = cursor.fetchall()

        # Asignaciones existentes
        cursor.execute("""
            SELECT 
                a.id_asignacion,
                u.id_usuario,
                CONCAT(u.nombre, ' ', u.apellido_paterno, ' ', u.apellido_materno) AS nombre_completo,
                u.rol,
                g.nombre_grupo,
                m.id_materia, m.nombre_materia
            FROM tbl_asignaciones a
            JOIN tbl_usuarios u ON a.id_usuario = u.id_usuario
            JOIN tbl_materias m ON a.id_materia = m.id_materia
            JOIN tbl_grupos g ON a.id_grupo = g.id_grupo
            ORDER BY g.nombre_grupo, u.nombre;
        """)
        datos = cursor.fetchall()

    conexion.close()
    return render_template('asignaciones_contenido.html',
                           usuarios=usuarios, materias=materias, grupos=grupos, datos=datos)
# ==============================
# ACTUALIZAR ASIGNACIÓN (cambiar materia)
# ==============================
@app.route('/actualizar_asignacion/<int:id_asignacion>', methods=['POST'])
def actualizar_asignacion(id_asignacion):
    data = request.get_json()
    nueva_materia = data.get('materia')

    if not nueva_materia:
        return jsonify({'status': 'error', 'message': 'No se especificó la materia.'})

    conexion = conectar_db()
    if not conexion:
        return jsonify({'status': 'error', 'message': 'Error al conectar a la base de datos.'})

    try:
        with conexion.cursor() as cursor:
            cursor.execute("""
                UPDATE tbl_asignaciones
                SET id_materia = %s
                WHERE id_asignacion = %s
            """, (nueva_materia, id_asignacion))
            conexion.commit()
        return jsonify({'status': 'success', 'message': 'Asignación actualizada correctamente.'})
    except Exception as e:
        print("Error en actualizar_asignacion:", e)
        return jsonify({'status': 'error', 'message': 'Error al actualizar la asignación.'})
    finally:
        conexion.close()


# ==============================
# ELIMINAR ASIGNACIÓN
# ==============================
@app.route('/eliminar_asignacion/<int:id_asignacion>', methods=['DELETE'])
def eliminar_asignacion(id_asignacion):
    conexion = conectar_db()
    if not conexion:
        return jsonify({'status': 'error', 'message': 'Error al conectar a la base de datos.'})

    try:
        with conexion.cursor() as cursor:
            cursor.execute("DELETE FROM tbl_asignaciones WHERE id_asignacion = %s", (id_asignacion,))
            conexion.commit()
        return jsonify({'status': 'success', 'message': 'Asignación eliminada correctamente.'})
    except Exception as e:
        print("Error al eliminar asignación:", e)
        return jsonify({'status': 'error', 'message': 'Error al eliminar la asignación.'})
    finally:
        conexion.close()


# GUARDAR USUARIO 
@app.route('/guardar_usuario', methods=['POST'])
def guardar_usuario():
    data = request.get_json()

    # Normalizar texto 
    def normalize(text):
        return text.strip().title() if text else ''

    nombre = normalize(data.get('nombre'))
    apellido_paterno = normalize(data.get('apellido_paterno'))
    apellido_materno = normalize(data.get('apellido_materno'))
    correo_institucional = data.get('correo_institucional', '').strip().lower()
    csp = data.get('csp', '').strip()
    rol = data.get('rol', '').strip().lower()
    password = data.get('password')
    confirmar_password = data.get('confirmar_password')

    # Validaciones básicas
    if not nombre or not apellido_paterno or not correo_institucional or not password:
        return jsonify({'status': 'error', 'message': 'Faltan campos obligatorios.'})
    if password != confirmar_password:
        return jsonify({'status': 'error', 'message': 'Las contraseñas no coinciden.'})

    # Cifrar contraseña
    password_hash = generate_password_hash(password)

    conexion = conectar_db()
    if not conexion:
        return jsonify({'status': 'error', 'message': 'No se pudo conectar con la base de datos.'})

    try:
        with conexion.cursor(pymysql.cursors.DictCursor) as cursor:
            # Verificar duplicados antes de insertar
            cursor.execute("""
                SELECT id_usuario FROM tbl_usuarios 
                WHERE correo_institucional = %s OR (csp != '' AND csp = %s)
            """, (correo_institucional, csp))
            duplicado = cursor.fetchone()

            if duplicado:
                return jsonify({
                    "status": "error",
                    "message": "El correo institucional o el número CSP ya están registrados por otro usuario."
                })

            # Insertar si no existe duplicado
            cursor.execute("""
                INSERT INTO tbl_usuarios
                (nombre, apellido_paterno, apellido_materno, csp, correo_institucional, password_hash, rol)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (
                nombre,
                apellido_paterno,
                apellido_materno,
                csp,
                correo_institucional,
                password_hash,
                rol
            ))
            conexion.commit()

        return jsonify({'status': 'success', 'message': f'{rol.capitalize()} agregado correctamente.'})

    except Exception as e:
        print("Error en guardar_usuario:", e)
        return jsonify({
            "status": "error",
            "message": "Error al registrar usuario. Detalle técnico: " + str(e)
        })

    finally:
        conexion.close()


# ==============================
# Obtener datos de un usuario
# ==============================
@app.route('/ver_usuario/<int:id_usuario>', methods=['GET'])
def ver_usuario(id_usuario):
    conexion = conectar_db()
    if not conexion:
        return jsonify({'status': 'error', 'message': 'No se pudo conectar a la base de datos'})

    try:
        with conexion.cursor() as cursor:
            cursor.execute("""
                SELECT id_usuario, nombre, apellido_paterno, apellido_materno,
                       csp, correo_institucional, rol
                FROM tbl_usuarios
                WHERE id_usuario = %s
            """, (id_usuario,))
            usuario = cursor.fetchone()

            if not usuario:
                return jsonify({'status': 'error', 'message': 'Usuario no encontrado'})

            # Si es docente u orientador, mostrar sus asignaciones
            if usuario['rol'] in ['docente', 'orientador']:
                cursor.execute("""
                    SELECT m.nombre_materia, g.nombre_grupo
                    FROM tbl_asignaciones a
                    JOIN tbl_materias m ON a.id_materia = m.id_materia
                    JOIN tbl_grupos g ON a.id_grupo = g.id_grupo
                    WHERE a.id_usuario = %s
                """, (id_usuario,))
                asignaciones = cursor.fetchall()
                usuario['asignaciones'] = asignaciones

        return jsonify(usuario)

    except Exception as e:
        print("Error al obtener usuario:", e)
        return jsonify({'status': 'error', 'message': str(e)})
    finally:
        conexion.close()


# Actualizar datos de usuario

@app.route('/actualizar_usuario/<int:id_usuario>', methods=['POST'])
def actualizar_usuario(id_usuario):
    data = request.get_json()
    nombre = data.get('nombre')
    apellido_paterno = data.get('apellido_paterno')
    apellido_materno = data.get('apellido_materno')
    csp = data.get('csp')
    correo_institucional = data.get('correo_institucional')

    if not all([nombre, apellido_paterno, apellido_materno, correo_institucional]):
        return jsonify({'status': 'error', 'message': 'Faltan campos obligatorios.'})

    conexion = conectar_db()
    if not conexion:
        return jsonify({'status': 'error', 'message': 'No se pudo conectar a la base de datos.'})

    try:
        with conexion.cursor() as cursor:
            cursor.execute("""
                UPDATE tbl_usuarios
                SET nombre=%s, apellido_paterno=%s, apellido_materno=%s,
                    csp=%s, correo_institucional=%s
                WHERE id_usuario=%s
            """, (nombre, apellido_paterno, apellido_materno, csp, correo_institucional, id_usuario))
            conexion.commit()

        return jsonify({'status': 'success', 'message': 'Usuario actualizado correctamente.'})

    except Exception as e:
        print("Error al actualizar usuario:", e)
        return jsonify({'status': 'error', 'message': 'Error al actualizar usuario.'})
    finally:
        conexion.close()


# Eliminar usuario

@app.route('/eliminar_usuario/<int:id_usuario>', methods=['DELETE'])
def eliminar_usuario(id_usuario):
    conexion = conectar_db()
    if not conexion:
        return jsonify({'status': 'error', 'message': 'No se pudo conectar a la base de datos.'})

    try:
        with conexion.cursor() as cursor:
            # Primero verificamos que exista
            cursor.execute("SELECT id_usuario FROM tbl_usuarios WHERE id_usuario = %s", (id_usuario,))
            usuario = cursor.fetchone()
            if not usuario:
                return jsonify({'status': 'error', 'message': 'El usuario no existe.'})

            # Si tiene asignaciones, eliminarlas primero
            cursor.execute("DELETE FROM tbl_asignaciones WHERE id_usuario = %s", (id_usuario,))

            # Luego eliminamos el usuario
            cursor.execute("DELETE FROM tbl_usuarios WHERE id_usuario = %s", (id_usuario,))
            conexion.commit()

        return jsonify({'status': 'success', 'message': 'Usuario eliminado correctamente.'})

    except Exception as e:
        print("Error al eliminar usuario:", e)
        return jsonify({'status': 'error', 'message': 'Error al eliminar usuario.'})
    finally:
        conexion.close()

# ==============================
# OBTENER MATERIAS POR GRADO
# ==============================
@app.route('/materias_por_grado/<int:id_grado>')
def materias_por_grado(id_grado):
    conexion = conectar_db()
    if not conexion:
        return jsonify([])

    try:
        with conexion.cursor() as cursor:
            cursor.execute("""
                SELECT id_materia, nombre_materia 
                FROM tbl_materias 
                WHERE id_grado = %s
                ORDER BY nombre_materia ASC
            """, (id_grado,))
            materias = cursor.fetchall()
        return jsonify(materias)
    except Exception as e:
        print("Error en materias_por_grado:", e)
        return jsonify([])
    finally:
        conexion.close()


# ==============================
# OBTENER GRUPOS POR GRADO
# ==============================
@app.route('/grupos_por_grado/<int:id_grado>')
def grupos_por_grado(id_grado):
    conexion = conectar_db()
    if not conexion:
        return jsonify([])

    try:
        with conexion.cursor() as cursor:
            cursor.execute("""
                SELECT id_grupo, nombre_grupo 
                FROM tbl_grupos 
                WHERE id_grado = %s
                ORDER BY nombre_grupo ASC
            """, (id_grado,))
            grupos = cursor.fetchall()
        return jsonify(grupos)
    except Exception as e:
        print("Error en grupos_por_grado:", e)
        return jsonify([])
    finally:
        conexion.close()


# ==============================
# ASIGNAR MATERIA A DOCENTE
# ==============================
@app.route('/asignar_materia_grupo', methods=['POST'])
def asignar_materia_grupo():
    data = request.get_json()
    id_docente = data.get('id_docente')
    id_materia = data.get('id_materia')
    id_grupo = data.get('id_grupo')

    if not all([id_docente, id_materia, id_grupo]):
        return jsonify({'status': 'error', 'message': 'Faltan datos para la asignación.'})

    conexion = conectar_db()
    if not conexion:
        return jsonify({'status': 'error', 'message': 'Error de conexión a la base de datos.'})

    try:
        with conexion.cursor() as cursor:
            # Evitar duplicados
            cursor.execute("""
                SELECT * FROM tbl_asignaciones
                WHERE id_usuario = %s AND id_materia = %s AND id_grupo = %s
            """, (id_docente, id_materia, id_grupo))
            existente = cursor.fetchone()
            if existente:
                return jsonify({'status': 'error', 'message': 'Esta asignación ya existe.'})

            cursor.execute("""
                INSERT INTO tbl_asignaciones (id_usuario, id_materia, id_grupo)
                VALUES (%s, %s, %s)
            """, (id_docente, id_materia, id_grupo))
            conexion.commit()

        return jsonify({'status': 'success', 'message': 'Asignación registrada correctamente.'})
    except Exception as e:
        print("Error en asignar_materia_grupo:", e)
        return jsonify({'status': 'error', 'message': 'Error al registrar la asignación.'})
    finally:
        conexion.close()

def calcular_estado_general(cursor, id_estudiante, id_grupo):
    cursor.execute("""
        SELECT 
            t.id_trabajo, t.valor_maximo, 
            ent.calificacion, ent.entregado, ent.justificado, t.suspension
        FROM tbl_trabajos t
        JOIN tbl_asignaciones a ON a.id_asignacion = t.id_asignacion
        LEFT JOIN tbl_entregas ent 
            ON ent.id_trabajo = t.id_trabajo AND ent.id_estudiante = %s
        WHERE a.id_grupo = %s
    """, (id_estudiante, id_grupo))
    trabajos = cursor.fetchall()

    if not trabajos:
        return "Sin datos"

    total = len(trabajos)
    entregados = sum(1 for t in trabajos if (t['entregado'] or t['justificado'] or t['suspension']))
    puntos_totales = sum(float(t['valor_maximo'] or 0) for t in trabajos)
    puntos_obtenidos = sum(float(t['calificacion'] or 0) for t in trabajos if t['calificacion'] is not None)
    porcentaje = (puntos_obtenidos / puntos_totales * 100) if puntos_totales > 0 else 0

    if entregados < total or porcentaje < 60:
        return "En rezago"
    elif porcentaje >= 90:
        return "Excelencia"
    elif porcentaje >= 70:
        return "Regular"
    else:
        return "En rezago"

# ==============================
# VER DETALLE DE GRUPO (ADMIN)
# ==============================
@app.route('/admin/grupo/<int:id_grupo>')
def admin_ver_grupo(id_grupo):
    if session.get('rol') != 'administrador':
        return jsonify({"status": "error", "message": "Acceso denegado"})

    conexion = conectar_db()
    if not conexion:
        return jsonify({"status": "error", "message": "Error de conexión"})

    try:
        with conexion.cursor(pymysql.cursors.DictCursor) as cursor:
            # Ordenar por número de lista, y si hay empates, por apellidos
            cursor.execute("""
                SELECT 
                    e.id_estudiante,
                    e.numero_lista,
                    CONCAT(e.nombre, ' ', e.apellido_paterno, ' ', e.apellido_materno) AS nombre_completo,
                    e.sexo,
                    e.correo_institucional
                FROM tbl_estudiantes e
                WHERE e.id_grupo = %s
                ORDER BY e.numero_lista ASC, e.apellido_paterno ASC, e.apellido_materno ASC, e.nombre ASC
            """, (id_grupo,))
            estudiantes = cursor.fetchall()

            lista = []
            for est in estudiantes:
                estado = calcular_estado_general(cursor, est['id_estudiante'], id_grupo)
                color = (
                    "danger" if estado == "En rezago"
                    else "success" if estado == "Excelencia"
                    else "warning" if estado == "Regular"
                    else "secondary"
                )
                lista.append({
                    "id_estudiante": est['id_estudiante'],
                    "numero_lista": est['numero_lista'],  # se usa para mostrar en la tabla
                    "nombre_completo": est['nombre_completo'],
                    "sexo": est['sexo'] or '—',
                    "correo_institucional": est['correo_institucional'] or '—',
                    "estado": estado,
                    "color": color
                })

        return jsonify({"status": "success", "estudiantes": lista})

    except Exception as e:
        print("Error en admin_ver_grupo:", e)
        return jsonify({"status": "error", "message": str(e)})

    finally:
        conexion.close()


# ==============================
# DETALLE DE ESTUDIANTE (ADMIN)
# ==============================
@app.route('/admin/estudiante/<int:id_estudiante>/<int:id_grupo>')
def admin_ver_estudiante(id_estudiante, id_grupo):
    if session.get('rol') != 'administrador':
        return jsonify({"status": "error", "message": "Acceso denegado"})

    conexion = conectar_db()
    if not conexion:
        return jsonify({"status": "error", "message": "Error de conexión"})

    try:
        with conexion.cursor(pymysql.cursors.DictCursor) as cursor:
            # Materias del grupo
            cursor.execute("""
                SELECT m.id_materia, m.nombre_materia
                FROM tbl_materias m
                JOIN tbl_grados g ON g.id_grado = m.id_grado
                JOIN tbl_grupos gr ON gr.id_grado = g.id_grado
                WHERE gr.id_grupo = %s
            """, (id_grupo,))
            materias = cursor.fetchall()

            resultado = {}

            for mat in materias:
                id_materia = mat['id_materia']
                nombre_materia = mat['nombre_materia']

                # Buscar asignación
                cursor.execute("""
                    SELECT id_asignacion FROM tbl_asignaciones
                    WHERE id_grupo=%s AND id_materia=%s
                """, (id_grupo, id_materia))
                asignacion = cursor.fetchone()

                if not asignacion:
                    resultado[nombre_materia] = {
                        "nombre": nombre_materia,
                        "trabajos_por_parcial": {"Primero": [], "Segundo": [], "Tercero": []},
                        "estado": "Materia no evaluable",
                        "color": "secondary"
                    }
                    continue

                id_asignacion = asignacion['id_asignacion']

                cursor.execute("""
                    SELECT 
                        t.id_trabajo, t.titulo, t.valor_maximo, t.semana, t.parcial,
                        ent.calificacion, ent.entregado, ent.justificado, t.suspension
                    FROM tbl_trabajos t
                    LEFT JOIN tbl_entregas ent 
                        ON ent.id_trabajo = t.id_trabajo AND ent.id_estudiante = %s
                    WHERE t.id_asignacion = %s
                    ORDER BY FIELD(t.parcial, 'Primero','Segundo','Tercero'), t.semana ASC
                """, (id_estudiante, id_asignacion))
                trabajos = cursor.fetchall()

                parciales = {"Primero": [], "Segundo": [], "Tercero": []}
                for t in trabajos:
                    parcial = t['parcial'] or "Sin parcial"
                    if parcial not in parciales:
                        continue
                    if t['suspension']:
                        t['observacion'] = "Suspendido"
                    elif t['justificado']:
                        t['observacion'] = "Justificado"
                    elif not t['entregado']:
                        t['observacion'] = "No entregado"
                    else:
                        t['observacion'] = "Entregado"
                    parciales[parcial].append(t)

                total = len(trabajos)
                entregados = sum(1 for t in trabajos if (t['entregado'] or t['justificado'] or t['suspension']))
                puntos_totales = sum(float(t['valor_maximo'] or 0) for t in trabajos)
                puntos_obtenidos = sum(float(t['calificacion'] or 0) for t in trabajos if t['calificacion'] is not None)
                porcentaje = (puntos_obtenidos / puntos_totales * 100) if puntos_totales > 0 else 0

                if total == 0:
                    estado, color = "Materia no evaluable", "secondary"
                elif entregados < total or porcentaje < 60:
                    estado, color = "Rezago", "danger"
                elif porcentaje >= 90:
                    estado, color = "Excelencia", "success"
                elif porcentaje >= 70:
                    estado, color = "Regular", "warning"
                else:
                    estado, color = "Rezago", "danger"

                resultado[nombre_materia] = {
                    "nombre": nombre_materia,
                    "trabajos_por_parcial": parciales,
                    "estado": estado,
                    "color": color
                }

        return jsonify({"status": "success", "materias": resultado})

    except Exception as e:
        print("Error en admin_ver_estudiante:", e)
        return jsonify({"status": "error", "message": str(e)})
    finally:
        conexion.close()


# ======================================================
# RUTAS DE GESTIÓN DE ESTUDIANTES (ADMIN)
# ======================================================

# Listar estudiantes de un grupo (para tabla de gestión)
@app.route('/admin/grupo_estudiantes/<int:id_grupo>', methods=['GET'])
def admin_grupo_estudiantes(id_grupo):
    if session.get('rol') != 'administrador':
        return jsonify({"status": "error", "message": "Acceso denegado"})
    try:
        conexion = conectar_db()
        if not conexion:
            return jsonify({"status": "error", "message": "Error de conexión"})
        with conexion.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute("""
                SELECT e.id_estudiante,
                       CONCAT(e.nombre, ' ', e.apellido_paterno, ' ', e.apellido_materno) AS nombre_completo,
                       e.sexo, e.correo_institucional
                FROM tbl_estudiantes e
                WHERE e.id_grupo = %s
                ORDER BY e.apellido_paterno, e.apellido_materno, e.nombre
            """, (id_grupo,))
            estudiantes = cursor.fetchall()
        conexion.close()
        return jsonify({"status": "success", "estudiantes": estudiantes})
    except Exception as e:
        print("Error en /admin/grupo_estudiantes:", e)
        return jsonify({"status": "error", "message": str(e)})


#Agregar nuevo estudiante
@app.route('/admin/agregar_estudiante', methods=['POST'])
def admin_agregar_estudiante():
    if session.get('rol') != 'administrador':
        return jsonify({"status": "error", "message": "Acceso denegado"})

    try:
        data = request.get_json()

        # Datos del formulario
        nombre = data.get('nombre')
        apellido_paterno = data.get('apellido_paterno')
        apellido_materno = data.get('apellido_materno')
        sexo = data.get('sexo')
        exp = data.get('exp')  # Expediente manual
        curp = data.get('curp')
        telefono = data.get('telefono')
        correo_institucional = data.get('correo_institucional')
        id_grupo = data.get('id_grupo')

        #  Validar campos obligatorios
        if not all([nombre, apellido_paterno, apellido_materno, correo_institucional, id_grupo, exp]):
            return jsonify({"status": "error", "message": "Faltan campos obligatorios"})

        conexion = conectar_db()
        if not conexion:
            return jsonify({"status": "error", "message": "Error al conectar con la base de datos"})

        with conexion.cursor(pymysql.cursors.DictCursor) as cursor:
            # Obtener número de lista consecutivo dentro del grupo
            cursor.execute("""
                SELECT COALESCE(MAX(numero_lista), 0) + 1 AS siguiente
                FROM tbl_estudiantes
                WHERE id_grupo = %s
            """, (id_grupo,))
            siguiente = cursor.fetchone()['siguiente']

            # Insertar nuevo estudiante
            cursor.execute("""
                INSERT INTO tbl_estudiantes 
                (numero_lista, exp, nombre, apellido_paterno, apellido_materno, sexo, curp, telefono, correo_institucional, id_grupo)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (siguiente, exp, nombre, apellido_paterno, apellido_materno, sexo, curp, telefono, correo_institucional, id_grupo))
            
            # Obtener el ID del nuevo estudiante
            nuevo_id_estudiante = cursor.lastrowid

            # Crear entregas vacías para todos los trabajos existentes del grupo
            cursor.execute("""
                SELECT t.id_trabajo
                FROM tbl_trabajos t
                JOIN tbl_asignaciones a ON a.id_asignacion = t.id_asignacion
                WHERE a.id_grupo = %s
            """, (id_grupo,))
            trabajos_existentes = cursor.fetchall()

            if trabajos_existentes:
                for t in trabajos_existentes:
                    cursor.execute("""
                        INSERT INTO tbl_entregas (id_trabajo, id_estudiante, calificacion, entregado, justificado)
                        VALUES (%s, %s, NULL, 0, 0)
                    """, (t['id_trabajo'], nuevo_id_estudiante))

            conexion.commit()

        conexion.close()
        return jsonify({"status": "success", "message": "Estudiante agregado correctamente"})

    except Exception as e:
        print("Error en /admin/agregar_estudiante:", e)
        return jsonify({"status": "error", "message": str(e)})

# Ver estudiante (para editar desde modal)
@app.route('/admin/ver_estudiante/<int:id_estudiante>', methods=['GET'])
def admin_ver_estudiante_datos(id_estudiante):
    if session.get('rol') != 'administrador':
        return jsonify({"status": "error", "message": "Acceso denegado"})
    try:
        conexion = conectar_db()
        if not conexion:
            return jsonify({"status": "error", "message": "Error de conexión"})
        with conexion.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute("SELECT * FROM tbl_estudiantes WHERE id_estudiante = %s", (id_estudiante,))
            est = cursor.fetchone()
        conexion.close()
        if est:
            return jsonify({"status": "success", "data": est})
        else:
            return jsonify({"status": "error", "message": "Estudiante no encontrado"})
    except Exception as e:
        print("Error en /admin/ver_estudiante:", e)
        return jsonify({"status": "error", "message": str(e)})


# Editar estudiante 
@app.route('/admin/editar_estudiante/<int:id_estudiante>', methods=['POST'])
def admin_editar_estudiante(id_estudiante):
    if session.get('rol') != 'administrador':
        return jsonify({"status": "error", "message": "Acceso denegado"})
    try:
        data = request.get_json()
        conexion = conectar_db()
        if not conexion:
            return jsonify({"status": "error", "message": "Error de conexión"})
        with conexion.cursor() as cursor:
            cursor.execute("""
                UPDATE tbl_estudiantes
                SET nombre=%s, apellido_paterno=%s, apellido_materno=%s,
                    sexo=%s, curp=%s, telefono=%s, correo_institucional=%s
                WHERE id_estudiante=%s
            """, (data['nombre'], data['apellido_paterno'], data['apellido_materno'],
                  data['sexo'], data['curp'], data['telefono'],
                  data['correo_institucional'], id_estudiante))
            conexion.commit()
        conexion.close()
        return jsonify({"status": "success", "message": "Estudiante actualizado correctamente"})
    except Exception as e:
        print("Error en /admin/editar_estudiante:", e)
        return jsonify({"status": "error", "message": str(e)})


# Eliminar estudiante 

@app.route('/admin/eliminar_estudiante/<int:id_estudiante>', methods=['DELETE'])
def eliminar_estudiante(id_estudiante):
    if session.get('rol') != 'administrador':
        return jsonify({"status": "error", "message": "Acceso denegado"})

    try:
        conexion = conectar_db()
        if not conexion:
            return jsonify({"status": "error", "message": "Error al conectar a la base de datos"})

        with conexion.cursor() as cursor:
            # Primero eliminar sus entregas (para evitar error de FK)
            cursor.execute("DELETE FROM tbl_entregas WHERE id_estudiante = %s", (id_estudiante,))
            
            # Luego eliminar el estudiante
            cursor.execute("DELETE FROM tbl_estudiantes WHERE id_estudiante = %s", (id_estudiante,))
            
            conexion.commit()

        conexion.close()
        return jsonify({"status": "success", "message": "Estudiante eliminado correctamente"})

    except Exception as e:
        print("Error al eliminar estudiante:", e)
        return jsonify({"status": "error", "message": str(e)})


#------------------------------
#------------------------------
#------------------------------
#------------------------------
# Panel docente
@app.route('/docente')
def docente_dashboard():
    if 'rol' not in session or session['rol'] != 'docente':
        flash("Acceso denegado. Solo docentes.", "danger")
        return redirect(url_for('login'))

    conexion = conectar_db()
    data_docente = {}
    if conexion:
        try:
            with conexion.cursor() as cursor:
                cursor.execute("""
                    SELECT a.id_asignacion, g.id_grupo, g.nombre_grupo, gr.nombre_grado, m.nombre_materia
                    FROM tbl_asignaciones a
                    JOIN tbl_grupos g ON a.id_grupo = g.id_grupo
                    JOIN tbl_grados gr ON g.id_grado = gr.id_grado
                    JOIN tbl_materias m ON a.id_materia = m.id_materia
                    WHERE a.id_usuario = %s
                    GROUP BY a.id_asignacion
                """, (session['id_usuario'],))
                grupos = cursor.fetchall()
                data_docente['grupos'] = grupos

                estudiantes_por_grupo = {}
                for grupo in grupos:
                    cursor.execute("""
                        SELECT id_estudiante, numero_lista, nombre, apellido_paterno, apellido_materno, exp
                        FROM tbl_estudiantes
                        WHERE id_grupo = %s
                        ORDER BY numero_lista ASC
                    """, (grupo['id_grupo'],))
                    estudiantes_por_grupo[grupo['id_grupo']] = cursor.fetchall()
                data_docente['estudiantes'] = estudiantes_por_grupo
        finally:
            conexion.close()

    return render_template('docente.html', nombre=session.get('usuario'), data=data_docente)



# Crear trabajo
@app.route('/crear_trabajo/<int:id_asignacion>', methods=['POST'])
def crear_trabajo(id_asignacion):
    data = request.get_json()
    conexion = conectar_db()
    id_trabajo = None
    estudiantes = []
    if conexion:
        try:
            with conexion.cursor(pymysql.cursors.DictCursor) as cursor:
                cursor.execute("""
                    INSERT INTO tbl_trabajos 
                    (id_asignacion, semana, periodo_inicio, periodo_fin, parcial, titulo, valor_maximo, fecha_creacion, suspension)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, NOW(), 0)
                """, (
                    id_asignacion,
                    data['semana'],
                    data['periodo_inicio'],
                    data['periodo_fin'],
                    data['parcial'],
                    data['titulo'],
                    data['valor_maximo']
                ))
                conexion.commit()
                id_trabajo = cursor.lastrowid
                cursor.execute("SELECT id_grupo FROM tbl_asignaciones WHERE id_asignacion=%s", (id_asignacion,))
                fila = cursor.fetchone()
                id_grupo = fila['id_grupo'] if fila else None
                if id_grupo:
                    cursor.execute("""
                        SELECT id_estudiante, nombre, apellido_paterno, apellido_materno, exp
                        FROM tbl_estudiantes
                        WHERE id_grupo = %s
                        ORDER BY numero_lista ASC
                    """, (id_grupo,))
                    estudiantes = cursor.fetchall()
                    for est in estudiantes:
                        cursor.execute("""
                            INSERT INTO tbl_entregas (id_trabajo, id_estudiante, calificacion, entregado, justificado)
                            VALUES (%s, %s, NULL, 0, 0)
                        """, (id_trabajo, est['id_estudiante']))
                    conexion.commit()
        finally:
            conexion.close()
    return jsonify({'status': 'success', 'id_trabajo': id_trabajo, 'estudiantes': estudiantes})


# Guardar calificaciones
@app.route('/guardar_calificaciones', methods=['POST'])
def guardar_calificaciones():
    resultados = request.get_json()
    conexion = conectar_db()
    if conexion:
        try:
            with conexion.cursor() as cursor:
                for r in resultados:
                    cursor.execute("""
                        UPDATE tbl_trabajos SET suspension = %s WHERE id_trabajo = %s
                    """, (r.get('suspension', 0), r['idTrabajo']))
                    cursor.execute("""
                        UPDATE tbl_entregas
                        SET calificacion = %s, entregado = %s, justificado = %s
                        WHERE id_trabajo = %s AND id_estudiante = %s
                    """, (r['puntaje'], int(r['entregado']), int(r.get('justificado', 0)), r['idTrabajo'], r['idEstudiante']))
                conexion.commit()
        finally:
            conexion.close()
    return jsonify({'status': 'success'})


# -----------------------------
# Seguimiento
# -----------------------------
@app.route('/seguimiento/<int:id_asignacion>', methods=['GET'])
def seguimiento_grupo(id_asignacion):
    conexion = conectar_db()
    if not conexion:
        return jsonify({'status': 'error', 'message': 'No se pudo conectar a la base de datos.'}), 500

    try:
        with conexion.cursor(pymysql.cursors.DictCursor) as cursor:
            # Obtener grupo al que pertenece la asignación
            cursor.execute("SELECT id_grupo FROM tbl_asignaciones WHERE id_asignacion = %s", (id_asignacion,))
            fila = cursor.fetchone()
            if not fila:
                return jsonify({'status': 'error', 'message': 'Asignación no encontrada.'})
            id_grupo = fila['id_grupo']

            # Traer todos los estudiantes del grupo y sus trabajos (aunque no tengan entregas)
            cursor.execute("""
                SELECT 
                    e.id_estudiante,
                    e.nombre,
                    e.apellido_paterno,
                    e.apellido_materno,
                    t.id_trabajo,
                    t.titulo,
                    t.semana,
                    t.valor_maximo,
                    t.parcial,
                    t.suspension,
                    DATE_FORMAT(t.periodo_inicio, '%%d/%%m/%%Y') AS periodo_inicio,
                    DATE_FORMAT(t.periodo_fin, '%%d/%%m/%%Y') AS periodo_fin,
                    en.calificacion,
                    en.entregado,
                    en.justificado
                FROM tbl_trabajos t
                JOIN tbl_asignaciones a ON t.id_asignacion = a.id_asignacion
                JOIN tbl_estudiantes e ON e.id_grupo = a.id_grupo
                LEFT JOIN tbl_entregas en ON en.id_trabajo = t.id_trabajo AND en.id_estudiante = e.id_estudiante
                WHERE t.id_asignacion = %s
                ORDER BY t.parcial, t.semana ASC, e.numero_lista ASC
            """, (id_asignacion,))
            datos = cursor.fetchall()

        return jsonify(datos)

    except Exception as e:
        print("Error en seguimiento:", e)
        return jsonify({'status': 'error', 'message': str(e)})

    finally:
        conexion.close()


# Eliminar trabajo
@app.route('/eliminar_trabajo/<int:id_trabajo>', methods=['DELETE'])
def eliminar_trabajo(id_trabajo):
    conexion = conectar_db()
    if not conexion:
        return jsonify({'status': 'error', 'message': 'Sin conexión a BD'})
    try:
        with conexion.cursor() as cursor:
            cursor.execute("DELETE FROM tbl_entregas WHERE id_trabajo = %s", (id_trabajo,))
            cursor.execute("DELETE FROM tbl_trabajos WHERE id_trabajo = %s", (id_trabajo,))
            conexion.commit()
        return jsonify({'status': 'success'})
    except Exception as e:
        print("Error al eliminar trabajo:", e)
        return jsonify({'status': 'error', 'message': str(e)})
    finally:
        conexion.close()



# PANEL ORIENTADOR
@app.route('/panel_orientador')
def panel_orientador():
    if session.get('rol') != 'orientador':
        flash("Acceso denegado. Solo orientadores.", "danger")
        return redirect(url_for('login'))

    id_orientador = session['id_usuario']
    nombre = session['usuario']

    conexion = conectar_db()
    if not conexion:
        flash("Error al conectar a la base de datos.", "danger")
        return redirect(url_for('login'))

    try:
        with conexion.cursor(pymysql.cursors.DictCursor) as cursor:
            # Grupos asignados al orientador
            cursor.execute("""
                SELECT DISTINCT g.id_grupo, gr.nombre_grado, g.nombre_grupo
                FROM tbl_asignaciones a
                JOIN tbl_grupos g ON g.id_grupo = a.id_grupo
                JOIN tbl_grados gr ON gr.id_grado = g.id_grado
                WHERE a.id_usuario = %s
            """, (id_orientador,))
            grupos = cursor.fetchall()
    finally:
        conexion.close()

    return render_template('orientador.html', nombre=nombre, grupos=grupos)



# GRUPO DEL ORIENTADOR 
@app.route('/panel_orientador/grupo/<int:id_grupo>')
def orientador_grupo(id_grupo):
    if session.get('rol') != 'orientador':
        return jsonify({"status": "error", "message": "Acceso denegado"})

    conexion = conectar_db()
    if not conexion:
        return jsonify({"status": "error", "message": "Error de conexión"})

    try:
        with conexion.cursor(pymysql.cursors.DictCursor) as cursor:
            # Ahora ordenamos por número de lista, no por apellido
            cursor.execute("""
                SELECT 
                    e.id_estudiante,
                    e.numero_lista,
                    CONCAT(e.nombre, ' ', e.apellido_paterno, ' ', e.apellido_materno) AS nombre_completo
                FROM tbl_estudiantes e
                WHERE e.id_grupo = %s
                ORDER BY e.numero_lista ASC
            """, (id_grupo,))
            estudiantes = cursor.fetchall()

            lista = []
            for est in estudiantes:
                id_est = est['id_estudiante']

                # Calcular estado general del estudiante
                cursor.execute("""
                    SELECT 
                        t.id_trabajo, t.valor_maximo, 
                        ent.calificacion, ent.entregado, ent.justificado, t.suspension
                    FROM tbl_trabajos t
                    JOIN tbl_asignaciones a ON a.id_asignacion = t.id_asignacion
                    LEFT JOIN tbl_entregas ent 
                        ON ent.id_trabajo = t.id_trabajo AND ent.id_estudiante = %s
                    WHERE a.id_grupo = %s
                """, (id_est, id_grupo))
                trabajos = cursor.fetchall()

                if not trabajos:
                    estado, color = "Sin datos", "secondary"
                else:
                    total = len(trabajos)
                    entregados = sum(1 for t in trabajos if (t['entregado'] or t['justificado'] or t['suspension']))
                    puntos_totales = sum(float(t['valor_maximo'] or 0) for t in trabajos)
                    puntos_obtenidos = sum(float(t['calificacion'] or 0) for t in trabajos if t['calificacion'] is not None)

                    porcentaje = (puntos_obtenidos / puntos_totales * 100) if puntos_totales > 0 else 0

                    if entregados < total or porcentaje < 60:
                        estado, color = "En rezago", "danger"
                    elif porcentaje >= 90:
                        estado, color = "Excelencia", "success"
                    elif porcentaje >= 70:
                        estado, color = "Regular", "warning"
                    else:
                        estado, color = "En rezago", "danger"

                lista.append({
                    "id_estudiante": id_est,
                    "numero_lista": est['numero_lista'],
                    "nombre_completo": est['nombre_completo'],
                    "estado": estado,
                    "color": color
                })

        # Nombres de estudiantes en rezago
        rezagos_list = [e['nombre_completo'] for e in lista if e['estado'] == 'En rezago']

        return jsonify({
            "status": "success",
            "estudiantes": lista,
            "rezagos": len(rezagos_list),
            "rezagos_list": rezagos_list
        })

    except Exception as e:
        print("Error en orientador_grupo:", e)
        return jsonify({"status": "error", "message": str(e)})

    finally:
        conexion.close()


# -----------------------------
# DETALLE DE UN ESTUDIANTE → MATERIAS Y TRABAJOS POR PARCIAL
# -----------------------------
@app.route('/panel_orientador/estudiante/<int:id_estudiante>/<int:id_grupo>')
def orientador_estudiante(id_estudiante, id_grupo):
    print(f"Ruta estudiante → Estudiante {id_estudiante}, Grupo {id_grupo}")

    if session.get('rol') != 'orientador':
        return jsonify({"status": "error", "message": "Acceso denegado"})

    conexion = conectar_db()
    if not conexion:
        return jsonify({"status": "error", "message": "Error de conexión"})

    try:
        with conexion.cursor(pymysql.cursors.DictCursor) as cursor:
            # Materias del grupo
            cursor.execute("""
                SELECT m.id_materia, m.nombre_materia
                FROM tbl_materias m
                JOIN tbl_grados g ON g.id_grado = m.id_grado
                JOIN tbl_grupos gr ON gr.id_grado = g.id_grado
                WHERE gr.id_grupo = %s
            """, (id_grupo,))
            materias = cursor.fetchall()

            resultado = {}

            for mat in materias:
                id_materia = mat['id_materia']
                nombre_materia = mat['nombre_materia']

                # Asignación docente
                cursor.execute("""
                    SELECT id_asignacion FROM tbl_asignaciones 
                    WHERE id_grupo=%s AND id_materia=%s
                """, (id_grupo, id_materia))
                asignacion = cursor.fetchone()

                if not asignacion:
                    resultado[nombre_materia] = {
                        "nombre": nombre_materia,
                        "trabajos_por_parcial": {"Primero": [], "Segundo": [], "Tercero": []},
                        "estado": "Materia no evaluable",
                        "color": "secondary"
                    }
                    continue

                id_asignacion = asignacion['id_asignacion']

                # Trabajos y entregas agrupados por parcial
                cursor.execute("""
                    SELECT 
                        t.id_trabajo, t.titulo, t.valor_maximo, t.semana, t.parcial,
                        ent.calificacion, ent.entregado, ent.justificado, t.suspension
                    FROM tbl_trabajos t
                    LEFT JOIN tbl_entregas ent 
                        ON ent.id_trabajo = t.id_trabajo AND ent.id_estudiante = %s
                    WHERE t.id_asignacion = %s
                    ORDER BY FIELD(t.parcial,'Primero','Segundo','Tercero'), t.semana ASC
                """, (id_estudiante, id_asignacion))
                trabajos = cursor.fetchall()

                parciales = {"Primero": [], "Segundo": [], "Tercero": []}

                for t in trabajos:
                    parcial = t['parcial'] or "Sin parcial"
                    if parcial not in parciales:
                        continue

                    if t['suspension']:
                        t['observacion'] = "Suspendido"
                    elif t['justificado']:
                        t['observacion'] = "Justificado"
                    elif not t['entregado']:
                        t['observacion'] = "No entregado"
                    else:
                        t['observacion'] = "Entregado"

                    parciales[parcial].append(t)

                # Cálculo general de materia
                total = len(trabajos)
                entregados = sum(1 for t in trabajos if (t['entregado'] or t['justificado'] or t['suspension']))
                puntos_totales = sum(float(t['valor_maximo'] or 0) for t in trabajos)
                puntos_obtenidos = sum(float(t['calificacion'] or 0) for t in trabajos if t['calificacion'] is not None)
                porcentaje = (puntos_obtenidos / puntos_totales * 100) if puntos_totales > 0 else 0

                if total == 0:
                    estado, color = "Materia no evaluable", "secondary"
                elif entregados < total or porcentaje < 60:
                    estado, color = "Rezago", "danger"
                elif porcentaje >= 90:
                    estado, color = "Excelencia", "success"
                elif porcentaje >= 70:
                    estado, color = "Regular", "warning"
                else:
                    estado, color = "Rezago", "danger"

                resultado[nombre_materia] = {
                    "nombre": nombre_materia,
                    "trabajos_por_parcial": parciales,
                    "estado": estado,
                    "color": color
                }

        return jsonify({"status": "success", "materias": resultado})

    except Exception as e:
        print("Error en orientador_estudiante:", e)
        return jsonify({"status": "error", "message": str(e)})

    finally:
        conexion.close()



# -----------------------------
# Logout
# -----------------------------
@app.route('/logout')
def logout():
    session.clear()
    flash("Sesión cerrada correctamente.", "info")
    return redirect(url_for('login'))


# -----------------------------
# Ejecutar app
# -----------------------------
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)

